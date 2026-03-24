require("dotenv").config();
const express = require("express");
const cron = require("node-cron");
const axios = require("axios");
const twilio = require("twilio");
const cors = require("cors");
const fs = require("fs");
const path = require("path");
const { v4: uuidv4 } = require("uuid");

const app = express();
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: false }));
app.use(express.static(path.join(__dirname, "public")));

const twilioClient = twilio(process.env.TWILIO_ACCOUNT_SID, process.env.TWILIO_AUTH_TOKEN);

const CONFIG = {
  twilioPhone:      process.env.TWILIO_PHONE_NUMBER,
  rickPhone:        process.env.RICK_PHONE,
  vedderPhone:      process.env.VEDDER_PHONE,
  appsScriptUrl:    process.env.APPS_SCRIPT_URL,
  appsScriptSecret: process.env.APPS_SCRIPT_SECRET,
  anthropicKey:     process.env.ANTHROPIC_API_KEY,
  elevenLabsKey:    process.env.ELEVENLABS_API_KEY,
  googleApiKey:     process.env.GOOGLE_API_KEY,
  port:             process.env.PORT || 3000,
  dataDir:          path.join(__dirname, "data"),
  audioDir:         path.join(__dirname, "audio"),
};

if (!fs.existsSync(CONFIG.dataDir))  fs.mkdirSync(CONFIG.dataDir);
if (!fs.existsSync(CONFIG.audioDir)) fs.mkdirSync(CONFIG.audioDir);

app.use("/audio", (req, res, next) => {
  res.set("Access-Control-Allow-Origin", "*");
  res.set("Cache-Control", "no-cache");
  next();
}, express.static(CONFIG.audioDir));

const FILES = {
  queue:       path.join(CONFIG.dataDir, "queue.json"),
  transcripts: path.join(CONFIG.dataDir, "transcripts.json"),
  learnings:   path.join(CONFIG.dataDir, "learnings.json"),
  stats:       path.join(CONFIG.dataDir, "stats.json"),
  training:    path.join(CONFIG.dataDir, "training.json"),
  system:      path.join(CONFIG.dataDir, "system.json"),
  callbacks:   path.join(CONFIG.dataDir, "callbacks.json"),
};

const log = {
  info:  (msg, meta = {}) => console.info(JSON.stringify({ level: "info",  msg, ...meta })),
  warn:  (msg, meta = {}) => console.warn(JSON.stringify({ level: "warn",  msg, ...meta })),
  error: (msg, meta = {}) => console.error(JSON.stringify({ level: "error", msg, ...meta })),
};

function readJson(file, fallback) {
  try { if (fs.existsSync(file)) return JSON.parse(fs.readFileSync(file, "utf8")); } catch {}
  return fallback;
}
function writeJson(file, data) { fs.writeFileSync(file, JSON.stringify(data, null, 2), "utf8"); }

function getSystem()  { return readJson(FILES.system,  { sarahEnabled: true }); }
function saveSystem(s) { writeJson(FILES.system, s); }
function isSarahEnabled() { return getSystem().sarahEnabled; }

function getStats() {
  return readJson(FILES.stats, {
    totalCalls: 0, transfers: 0,
    rickTransfers: 0, vedderTransfers: 0,
    noAnswers: 0, voicemails: 0, hangups: 0,
    nextTransferTo: "rick",
  });
}
function saveStats(s) { writeJson(FILES.stats, s); }

function getQueue() {
  return readJson(FILES.queue, { items: [], active: false, currentIndex: 0, paused: false });
}
function saveQueue(q) { writeJson(FILES.queue, q); }

function saveTranscript(t) {
  const all = readJson(FILES.transcripts, []);
  all.unshift(t);
  writeJson(FILES.transcripts, all.slice(0, 200));
}

function getLearnings() {
  return readJson(FILES.learnings, { insights: [], lastUpdated: null, totalAnalyzed: 0 });
}
function saveLearnings(l) { writeJson(FILES.learnings, l); }

function getTraining() {
  return readJson(FILES.training, { videos: [], techniques: [], lastUpdated: null });
}
function saveTraining(t) { writeJson(FILES.training, t); }

const activeCalls = {};
let queueProcessing = false;

setInterval(() => {
  axios.get(`http://localhost:${CONFIG.port}/ping`).catch(() => {});
}, 280000);
app.get("/ping", (req, res) => res.send("ok"));

function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

// ─── ElevenLabs TTS ───────────────────────────────────────────────────────────

async function sarahSpeak(text, reqHost) {
  try {
    const cleanText = text
      .replace(/&/g, "and")
      .replace(/\.\.\./g, " ")
      .replace(/—/g, ", ")
      .replace(/[<>]/g, "")
      .trim();

    const response = await axios.post(
      "https://api.elevenlabs.io/v1/text-to-speech/cgSgspJ2msm6clMCkdW9",
      {
        text: cleanText,
        model_id: "eleven_turbo_v2",
        voice_settings: {
          stability: 0.35,
          similarity_boost: 0.82,
          style: 0.45,
          use_speaker_boost: true,
        },
      },
      {
        headers: {
          "xi-api-key": CONFIG.elevenLabsKey,
          "Content-Type": "application/json",
          Accept: "audio/mpeg",
        },
        responseType: "arraybuffer",
        timeout: 20000,
      }
    );

    if (!response.data || response.data.byteLength < 100) {
      log.warn("ElevenLabs empty audio");
      return null;
    }

    const audioId   = uuidv4();
    const audioFile = path.join(CONFIG.audioDir, `${audioId}.mp3`);
    fs.writeFileSync(audioFile, Buffer.from(response.data));

    setTimeout(() => { try { fs.unlinkSync(audioFile); } catch {} }, 300000);

    const audioUrl = `https://${reqHost}/audio/${audioId}.mp3`;
    log.info("ElevenLabs audio saved", { bytes: response.data.byteLength, url: audioUrl });
    return audioUrl;
  } catch (err) {
    log.error("ElevenLabs failed", { status: err.response?.status, err: err.message });
    return null;
  }
}

function buildTwiml(audioUrl, fallbackText, gatherAction) {
  const safe = (fallbackText || "")
    .replace(/&/g, "and")
    .replace(/[<>'"]/g, "")
    .replace(/\.\.\./g, " ")
    .replace(/—/g, ", ")
    .substring(0, 300);

  const playOrSay = audioUrl
    ? `<Play>${audioUrl}</Play>`
    : `<Say voice="Polly.Joanna-Neural" rate="92%">${safe}</Say>`;

  return `<?xml version="1.0" encoding="UTF-8"?>
<Response>
  ${playOrSay}
  <Gather input="speech" timeout="5" speechTimeout="2" action="${gatherAction}" method="POST">
    <Say> </Say>
  </Gather>
  <Redirect method="POST">${gatherAction}</Redirect>
</Response>`;
}

// ─── Google Places / YouTube ──────────────────────────────────────────────────

async function fetchYouTubeInfo(videoUrl) {
  const videoIdMatch = videoUrl.match(/(?:v=|youtu\.be\/)([a-zA-Z0-9_-]{11})/);
  if (!videoIdMatch) throw new Error("Invalid YouTube URL");
  const videoId = videoIdMatch[1];
  const res = await axios.get("https://www.googleapis.com/youtube/v3/videos", {
    params: { id: videoId, part: "snippet", key: CONFIG.googleApiKey },
    timeout: 10000,
  });
  const video = res.data.items?.[0];
  if (!video) throw new Error("Video not found");
  return {
    videoId,
    title: video.snippet.title,
    channel: video.snippet.channelTitle,
    description: video.snippet.description?.substring(0, 500) || "",
    url: videoUrl,
  };
}

async function extractTechniques(videoInfo) {
  const res = await axios.post(
    "https://api.anthropic.com/v1/messages",
    {
      model: "claude-haiku-4-5",
      max_tokens: 400,
      messages: [{
        role: "user",
        content: `Extract 3-5 specific actionable sales techniques from this video for an AI agent named Sarah who cold calls local businesses to sell website design services starting at $450 one-time plus $50 per month.

Video: "${videoInfo.title}" by ${videoInfo.channel}
Description: ${videoInfo.description}

Return only the techniques, one per line, starting with a verb. Make them specific to selling websites to local small businesses.`,
      }],
    },
    {
      headers: { "x-api-key": CONFIG.anthropicKey, "anthropic-version": "2023-06-01", "content-type": "application/json" },
      timeout: 30000,
    }
  );
  return res.data.content[0].text.trim().split("\n").filter(t => t.trim().length > 0);
}

// ─── Follow-up texter ─────────────────────────────────────────────────────────

async function getTodaysFollowUps() {
  try {
    const res = await axios.get(CONFIG.appsScriptUrl, {
      params: { secret: CONFIG.appsScriptSecret },
      timeout: 15000,
    });
    return (res.data.leads || []).filter(l => {
      const status = (l.status || "").toLowerCase();
      return status !== "fuck em" && status !== "lost";
    });
  } catch (err) {
    log.error("Failed to fetch follow-ups", { err: err.message });
    return [];
  }
}

async function sendFollowUpText(repName, repPhone, leads) {
  if (!leads.length) {
    await twilioClient.messages.create({
      body: `Good morning ${repName}! 🌅 No follow-ups today. Go find some fresh leads! 💪`,
      from: CONFIG.twilioPhone, to: repPhone,
    });
    return;
  }
  const list = leads.map((l, i) => {
    const notes = l.notes ? `\n   📝 ${l.notes.substring(0, 80)}${l.notes.length > 80 ? "..." : ""}` : "";
    return `${i + 1}. ${l.name}\n   📞 ${l.phone}${notes}`;
  }).join("\n\n");
  await twilioClient.messages.create({
    body: `Good morning ${repName}! ☀️ You have ${leads.length} follow-up${leads.length !== 1 ? "s" : ""} today:\n\n${list}\n\n💰 Go close some deals!`,
    from: CONFIG.twilioPhone, to: repPhone,
  });
}

async function runFollowUpTexter() {
  log.info("Running follow-up texter");
  const leads = await getTodaysFollowUps();
  const rickLeads   = leads.filter(l => (l.contactedBy || "").toLowerCase().includes("rick"));
  const vedderLeads = leads.filter(l => (l.contactedBy || "").toLowerCase().includes("vedder"));
  const unassigned  = leads.filter(l => { const cb = (l.contactedBy || "").toLowerCase(); return !cb.includes("rick") && !cb.includes("vedder"); });
  await Promise.all([
    sendFollowUpText("Rick",   CONFIG.rickPhone,   [...rickLeads, ...unassigned]),
    sendFollowUpText("Vedder", CONFIG.vedderPhone, vedderLeads),
  ]);
}

cron.schedule("30 14 * * 1-5", runFollowUpTexter, { timezone: "America/New_York" });

// ─── Round robin ──────────────────────────────────────────────────────────────

function getNextTransfer() {
  const stats  = getStats();
  const isRick = stats.nextTransferTo === "rick";
  const phone  = isRick ? CONFIG.rickPhone  : CONFIG.vedderPhone;
  const name   = isRick ? "Rick" : "Vedder";
  stats.nextTransferTo = isRick ? "vedder" : "rick";
  stats.transfers++;
  if (isRick) stats.rickTransfers++; else stats.vedderTransfers++;
  saveStats(stats);
  return { phone, name };
}

// ─── Industry detection ───────────────────────────────────────────────────────

function detectIndustry(name) {
  const n = name.toLowerCase();
  if (/barber|cuts|fade|shave|clipper|razor/.test(n))          return "barbershop";
  if (/salon|beauty|nail|lash|brow|spa|blowout|hair/.test(n)) return "salon";
  if (/dog|pet|groom|paw|pup|pooch|woof|fluff/.test(n))       return "pet_grooming";
  if (/hvac|heat|cool|air|furnace|ac |duct/.test(n))          return "hvac";
  if (/auto|car|truck|motor|garage|mechanic|tire/.test(n))    return "auto";
  if (/landscap|lawn|mow|garden|tree|mulch|sod/.test(n))      return "landscaping";
  if (/clean|maid|janitor|sweep|spotless/.test(n))            return "cleaning";
  if (/restaur|food|eat|diner|cafe|pizza|burger/.test(n))     return "restaurant";
  if (/plumb|pipe|drain|sewer/.test(n))                       return "plumbing";
  if (/electric|wiring|panel|volt/.test(n))                   return "electrical";
  if (/paint|coat|wall/.test(n))                              return "painting";
  if (/roof|shingle|gutter/.test(n))                          return "roofing";
  return "general";
}

function getIndustryPitch(industry, businessName) {
  const pitches = {
    barbershop:   `For barbershops, a website lets clients book appointments online 24/7. Most of your competitors don't have that yet. We can integrate booking right into the site so ${businessName} never loses a walk-in again.`,
    salon:        `For salons, we build sites that showcase your work with a portfolio gallery, online booking, and pricing. Clients research salons online before they ever call — without a website ${businessName} is invisible to them.`,
    pet_grooming: `Pet owners are incredibly loyal once they find a groomer they trust — but they find them online first. We build sites with appointment booking, service menus, and photo galleries that convert visitors to regulars.`,
    hvac:         `HVAC is a high-ticket service and people only search when they need you urgently. Without a website ${businessName} is losing emergency calls to competitors right now.`,
    auto:         `Auto repair customers always check websites before choosing a shop. We build sites for shops like ${businessName} with services listed, hours, location, and reviews that build instant trust.`,
    landscaping:  `Homeowners searching for landscapers go straight to Google — if ${businessName} doesn't have a website you're invisible to that entire market.`,
    cleaning:     `A professional website for ${businessName} with testimonials, services listed, and easy booking converts searchers into recurring clients automatically.`,
    restaurant:   `Restaurants without websites lose customers to apps taking a cut of every order. We build direct sites with menus, hours, and reservation links.`,
    plumbing:     `Plumbing is urgent — people search when pipes burst at midnight. Without a website ${businessName} misses every one of those emergency calls.`,
    electrical:   `A professional website for ${businessName} that shows credentials, service areas, and reviews converts searchers into booked jobs before they call a competitor.`,
    painting:     `Painting is a visual business — your work sells itself, but only if people can see it. We build sites with photo galleries and quote request forms that generate leads while you work.`,
    roofing:      `Roofing jobs are high ticket and homeowners research heavily before choosing. A website for ${businessName} with project photos and a free estimate form captures leads your competitors are getting right now.`,
    general:      `Most local businesses are losing customers to competitors who show up online first. A professional website for ${businessName} puts you on the map and captures leads 24/7.`,
  };
  return pitches[industry] || pitches.general;
}

function getTimeOfDayTone() {
  const hour = new Date().getHours();
  if (hour < 10) return "energetic and warm — keep it quick and upbeat";
  if (hour < 12) return "confident and direct — morning energy";
  if (hour < 14) return "friendly and brief — respect their time";
  if (hour < 17) return "relaxed and conversational — people are more receptive";
  return "warm and casual — be friendly not pushy";
}

// ─── Sarah's prompt ───────────────────────────────────────────────────────────

function buildSarahPrompt(businessName, isCallback = false) {
  const learnings = getLearnings();
  const training  = getTraining();
  const industry  = detectIndustry(businessName);
  const tone      = getTimeOfDayTone();
  const pitch     = getIndustryPitch(industry, businessName);

  const learnedInsights = learnings.insights.length
    ? "\nLEARNED FROM SUCCESSFUL CALLS:\n" + learnings.insights.slice(0, 5).map(i => "• " + i).join("\n") + "\n"
    : "";

  const trainedTechniques = training.techniques.length
    ? "\nTECHNIQUES FROM SALES TRAINING:\n" + training.techniques.slice(0, 8).map(t => "• " + t).join("\n") + "\n"
    : "";

  const callbackIntro = isCallback
    ? `This is a CALLBACK — they already spoke with you and booked this time. They ARE interested. Open with: "hey! it's Sarah from RLS Web Design... calling back just like we said. is now still good?"`
    : "";

  return `You are Sarah, a 25 year old sales rep for RLS Web Design. You call local businesses to show them a free custom website demo. You are warm, confident, casual, and genuinely friendly — like a real person not a robot.

${callbackIntro}

TONE: Be ${tone}
INDUSTRY: ${industry}
PITCH: ${pitch}

THE OFFER:
• Free custom demo website — no commitment to look at it
• Websites start at $450 one-time + $50/month
• We handle everything — design, hosting, updates, booking systems
${learnedInsights}${trainedTechniques}
OBJECTIONS — adapt naturally, never read word for word:
• "Not interested" → "oh totally, I get it... we actually already built the site though, takes 30 seconds to look at. can I text it to you real quick?"
• "I have a website" → "oh nice! ours might still be an upgrade... mind if I send it over just to compare? zero obligation"
• "Too busy" → "yeah for sure, super quick — we made something for free and I just need like 30 seconds"
• "How much?" → "starts at $450 one time then $50 a month... but look at the free demo first — if you don't love it you don't pay anything"
• "Send email" → "yeah absolutely... I'll text you the link right now. hey can I also get you on with our specialist real quick?"
• "I have a guy" → "no worries at all... totally free option to compare. let me text you the demo, no strings attached"
• Very rude → say exactly: HANG_UP

COMMANDS — say these exactly:
• They say yes or want to know more → TRANSFER_NOW
• They want demo texted → TEXT_DEMO then keep talking
• They want callback at specific time → BOOK_CALLBACK:[time]
• End politely → HANG_UP

SPEECH RULES:
• Use "..." for natural pauses — "yeah... I totally get that"
• Use "—" for direction changes — "we could — actually yeah let me just text it to you"
• Write CASUALLY: yeah, totally, oh wow, honestly, look, hey, so
• NEVER write perfect corporate sentences
• Keep ALL responses 1-3 sentences max
• Don't give up until 3 clear rejections`;
}

// ─── Rep briefing ─────────────────────────────────────────────────────────────

async function sendRepBriefing(repPhone, repName, callData) {
  const { businessName, phone, transcript, industry, callDuration } = callData;
  const transcriptText = (transcript || []).map(t => `${t.speaker}: ${t.text}`).join("\n");

  let briefing = "They expressed interest in a demo website.";
  try {
    const res = await axios.post(
      "https://api.anthropic.com/v1/messages",
      {
        model: "claude-haiku-4-5",
        max_tokens: 150,
        messages: [{ role: "user", content: `Analyze this sales call and give a 2-3 sentence briefing for the sales rep about to take the transfer. What interested them, their mood, one tip for closing.\n\nBusiness: ${businessName}\nIndustry: ${industry}\nTranscript:\n${transcriptText}\n\nReturn only the briefing, no labels.` }],
      },
      {
        headers: { "x-api-key": CONFIG.anthropicKey, "anthropic-version": "2023-06-01", "content-type": "application/json" },
        timeout: 10000,
      }
    );
    briefing = res.data.content[0].text.trim();
  } catch {}

  try {
    await twilioClient.messages.create({
      body: `🔥 INCOMING TRANSFER — Pick up NOW!\n\nBusiness: ${businessName}\n📞 ${phone}\nIndustry: ${industry}\nTalk time: ${callDuration}s\n\n📋 ${briefing}\n\n💡 Connecting now!`,
      from: CONFIG.twilioPhone,
      to: repPhone,
    });
  } catch (err) {
    log.warn("Briefing text failed", { err: err.message });
  }
}

// ─── Analyze successful call ──────────────────────────────────────────────────

async function analyzeSuccessfulCall(transcript, businessName) {
  try {
    const learnings = getLearnings();
    const transcriptText = (transcript || []).map(t => `${t.speaker}: ${t.text}`).join("\n");
    const res = await axios.post(
      "https://api.anthropic.com/v1/messages",
      {
        model: "claude-haiku-4-5",
        max_tokens: 120,
        messages: [{ role: "user", content: `Extract ONE specific actionable insight (1-2 sentences) from this successful sales call that made it work.\n\nBusiness: ${businessName}\nTranscript:\n${transcriptText}\n\nReturn only the insight.` }],
      },
      {
        headers: { "x-api-key": CONFIG.anthropicKey, "anthropic-version": "2023-06-01", "content-type": "application/json" },
        timeout: 15000,
      }
    );
    const insight = res.data.content[0].text.trim();
    learnings.insights.unshift(insight);
    learnings.insights = learnings.insights.slice(0, 25);
    learnings.lastUpdated = new Date().toISOString();
    learnings.totalAnalyzed++;
    saveLearnings(learnings);
  } catch (err) {
    log.warn("Analysis failed", { err: err.message });
  }
}

// ─── Claude response with filler ─────────────────────────────────────────────

const FILLERS = [
  "mmm, let me think about that for just a second.",
  "that's a good point, give me one moment.",
  "sure, absolutely — one second.",
  "mm-hmm, yeah —",
];

async function getClaudeResponse(callSid, userSpeech, businessName, isCallback = false) {
  if (!activeCalls[callSid]) {
    activeCalls[callSid] = {
      businessName, isCallback,
      history: [], transcript: [],
      noCount: 0, startTime: Date.now(),
      industry: detectIndustry(businessName),
    };
  }

  const call = activeCalls[callSid];

  if (userSpeech) {
    call.history.push({ role: "user", content: userSpeech });
    call.transcript.push({ speaker: "LEAD", text: userSpeech, time: new Date().toISOString() });
    const lower = userSpeech.toLowerCase();
    if (/not interested|no thank|don't want|stop calling|remove/.test(lower)) call.noCount++;
    if (call.noCount >= 3) return "HANG_UP";
  }

  const claudePromise = axios.post(
    "https://api.anthropic.com/v1/messages",
    {
      model: "claude-haiku-4-5",
      max_tokens: 120,
      system: buildSarahPrompt(businessName, isCallback),
      messages: call.history,
    },
    {
      headers: { "x-api-key": CONFIG.anthropicKey, "anthropic-version": "2023-06-01", "content-type": "application/json" },
      timeout: 12000,
    }
  );

  let reply;
  try {
    const winner = await Promise.race([
      claudePromise,
      new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), 2500)),
    ]);
    reply = winner.data.content[0].text.trim();
  } catch {
    reply = null;
  }

  if (!reply) {
    const filler = FILLERS[Math.floor(Math.random() * FILLERS.length)];
    call.transcript.push({ speaker: "SARAH", text: filler, time: new Date().toISOString() });
    try {
      const res = await claudePromise;
      reply = res.data.content[0].text.trim();
    } catch {
      reply = "let me have our specialist follow up with you directly. have a great day!";
    }
  }

  call.history.push({ role: "assistant", content: reply });
  call.transcript.push({ speaker: "SARAH", text: reply, time: new Date().toISOString() });
  return reply;
}

// ─── Queue processor ──────────────────────────────────────────────────────────

async function processNextInQueue(host, protocol) {
  if (!isSarahEnabled()) return;
  const queue = getQueue();
  if (!queue.active || queue.paused || queueProcessing) return;
  if (queue.currentIndex >= queue.items.length) {
    queue.active = false;
    saveQueue(queue);
    return;
  }

  const item = queue.items[queue.currentIndex];
  if (item.status !== "pending") {
    queue.currentIndex++;
    saveQueue(queue);
    setTimeout(() => processNextInQueue(host, protocol), 500);
    return;
  }

  queueProcessing = true;
  item.status    = "calling";
  item.startedAt = new Date().toISOString();
  saveQueue(queue);

  const stats = getStats();
  stats.totalCalls++;
  saveStats(stats);

  try {
    const call = await twilioClient.calls.create({
      to:   item.phone,
      from: CONFIG.twilioPhone,
      url:  `${protocol}://${host}/voice/start?business=${encodeURIComponent(item.name)}&queueId=${item.id}`,
      statusCallback:       `${protocol}://${host}/voice/status?queueId=${item.id}`,
      statusCallbackMethod: "POST",
      timeout: 30,
      machineDetection: "DetectMessageEnd",
      asyncAmdStatusCallback: `${protocol}://${host}/voice/amd?business=${encodeURIComponent(item.name)}`,
    });
    item.callSid = call.sid;
    saveQueue(queue);
  } catch (err) {
    log.error("Queue call failed", { err: err.message });
    item.status = "failed";
    item.error  = err.message;
    queue.currentIndex++;
    queueProcessing = false;
    saveQueue(queue);
    setTimeout(() => processNextInQueue(host, protocol), 3000);
  }
}

// ─── Voice Routes ─────────────────────────────────────────────────────────────

app.post("/voice/amd", async (req, res) => {
  const { AnsweredBy } = req.body;
  const businessName   = decodeURIComponent(req.query.business || "your business");
  const host           = req.get("host");

  if (AnsweredBy === "machine_start" || AnsweredBy === "fax") {
    const stats = getStats();
    stats.voicemails++;
    saveStats(stats);

    const vmText = `hey! this is Sarah from RLS Web Design, sorry I missed you. I was calling because we built ${businessName} a free demo website and wanted to show it to you. I'll text you the link right now. give us a call back whenever, no pressure. have a great day!`;
    const audioUrl = await sarahSpeak(vmText, host);

    res.type("text/xml").send(`<?xml version="1.0" encoding="UTF-8"?>
<Response>
  ${audioUrl ? `<Play>${audioUrl}</Play>` : `<Say voice="Polly.Joanna-Neural" rate="92%">${vmText.replace(/[<>&'"]/g,"")}</Say>`}
  <Hangup/>
</Response>`);

    try {
      await twilioClient.messages.create({
        body: `hey! it's Sarah from RLS Web Design 👋 I just tried calling but missed you — we built you a free demo website, check it out whenever you get a chance. no pressure at all!`,
        from: CONFIG.twilioPhone,
        to:   req.body.To || "",
      });
    } catch {}
  } else {
    res.sendStatus(200);
  }
});

app.post("/voice/start", async (req, res) => {
  const businessName = decodeURIComponent(req.query.business || "your business");
  const callSid      = req.body.CallSid;
  const isCallback   = req.query.isCallback === "true";
  const host         = req.get("host");

  log.info("Voice start", { callSid, businessName, isCallback });

  const opener = isCallback
    ? `hey! it's Sarah from RLS Web Design... calling back just like we said. is now still a good time?`
    : `hey there, my name's Sarah, I'm calling from RLS Web Design. am I speaking with someone from ${businessName}?`;

  const gatherAction = `/voice/respond?business=${encodeURIComponent(businessName)}&callSid=${callSid}&isCallback=${isCallback}`;
  const audioUrl     = await sarahSpeak(opener, host);
  res.type("text/xml").send(buildTwiml(audioUrl, opener, gatherAction));
});

app.post("/voice/respond", async (req, res) => {
  const businessName = decodeURIComponent(req.query.business || "your business");
  const callSid      = req.body.CallSid || req.query.callSid;
  const isCallback   = req.query.isCallback === "true";
  const speechResult = req.body.SpeechResult || "";
  const host         = req.get("host");
  const protocol     = req.headers["x-forwarded-proto"] || "https";

  log.info("Speech received", { callSid, speech: speechResult.substring(0, 80) });

  try {
    const reply        = await getClaudeResponse(callSid, speechResult || "hello", businessName, isCallback);
    const call         = activeCalls[callSid];
    const gatherAction = `/voice/respond?business=${encodeURIComponent(businessName)}&callSid=${callSid}&isCallback=${isCallback}`;

    if (reply === "HANG_UP") {
      if (call) {
        saveTranscript({ id: uuidv4(), businessName, outcome: "hung_up", transcript: call.transcript, createdAt: new Date().toISOString() });
        delete activeCalls[callSid];
      }
      const goodbyeText = "no problem at all! you have a great rest of your day, take care!";
      const audioUrl    = await sarahSpeak(goodbyeText, host);
      return res.type("text/xml").send(`<?xml version="1.0" encoding="UTF-8"?>
<Response>
  ${audioUrl ? `<Play>${audioUrl}</Play>` : `<Say voice="Polly.Joanna-Neural">No problem, have a great day!</Say>`}
  <Hangup/>
</Response>`);
    }

    if (reply === "TRANSFER_NOW") {
      const { phone: transferPhone, name: transferName } = getNextTransfer();
      if (call) {
        const duration = Math.round((Date.now() - call.startTime) / 1000);
        await sendRepBriefing(transferPhone, transferName, {
          businessName, phone: req.body.To || req.body.Called || "",
          transcript: call.transcript, industry: call.industry, callDuration: duration,
        });
        await analyzeSuccessfulCall(call.transcript, businessName);
        saveTranscript({ id: uuidv4(), businessName, outcome: "transferred", transferredTo: transferName, transcript: call.transcript, duration, createdAt: new Date().toISOString() });
        delete activeCalls[callSid];
      }
      const transferText = `oh awesome... yeah let me get ${transferName} on the line for you right now, he's gonna walk you through everything. one second!`;
      const audioUrl     = await sarahSpeak(transferText, host);
      return res.type("text/xml").send(`<?xml version="1.0" encoding="UTF-8"?>
<Response>
  ${audioUrl ? `<Play>${audioUrl}</Play>` : `<Say voice="Polly.Joanna-Neural">Let me connect you with ${transferName} right now!</Say>`}
  <Dial callerId="${CONFIG.twilioPhone}" timeout="20" action="/voice/transfer-fallback?business=${encodeURIComponent(businessName)}&phone=${encodeURIComponent(req.body.To || "")}" method="POST">
    <Number>${transferPhone}</Number>
  </Dial>
</Response>`);
    }

    if (reply.startsWith("BOOK_CALLBACK:")) {
      const requestedTime = reply.replace("BOOK_CALLBACK:", "").trim();
      const { name: repName, phone: repPhone } = getNextTransfer();
      const callbacks = readJson(FILES.callbacks, []);
      callbacks.push({ id: uuidv4(), businessName, phone: req.body.To || "", requestedTime, repName, createdAt: new Date().toISOString() });
      writeJson(FILES.callbacks, callbacks);
      try {
        await twilioClient.messages.create({
          body: `📅 Callback scheduled!\n\nBusiness: ${businessName}\nRequested: ${requestedTime}\nAssigned to: ${repName}`,
          from: CONFIG.twilioPhone, to: repPhone,
        });
        await twilioClient.messages.create({
          body: `hey! it's Sarah from RLS Web Design — I've got you scheduled for a callback ${requestedTime}. our specialist will call you then to walk you through your free demo. talk soon! 😊`,
          from: CONFIG.twilioPhone, to: req.body.To || "",
        });
      } catch {}
    }

    if (reply.startsWith("TEXT_DEMO")) {
      try {
        await twilioClient.messages.create({
          body: `hey! it's Sarah from RLS Web Design 👋 here's the free demo website we built for you — take a look and let us know what you think!`,
          from: CONFIG.twilioPhone,
          to:   req.body.To || req.body.Called || "",
        });
      } catch {}
    }

    const cleanReply = reply.replace(/^(TRANSFER_NOW|HANG_UP|TEXT_DEMO|BOOK_CALLBACK:[^\n]*)/i, "").trim();
    const sayText    = cleanReply || "so yeah... what do you think, would it be worth taking a quick look?";
    const audioUrl   = await sarahSpeak(sayText, host);
    res.type("text/xml").send(buildTwiml(audioUrl, sayText, gatherAction));

  } catch (err) {
    log.error("Respond error", { err: err.message });
    const sorryText = "oh gosh I'm sorry about that, let me have someone from our team reach out to you directly. have a great day!";
    const audioUrl  = await sarahSpeak(sorryText, host);
    return res.type("text/xml").send(`<?xml version="1.0" encoding="UTF-8"?>
<Response>
  ${audioUrl ? `<Play>${audioUrl}</Play>` : `<Say voice="Polly.Joanna-Neural">I apologize, someone will follow up shortly!</Say>`}
  <Hangup/>
</Response>`);
  }
});

app.post("/voice/transfer-fallback", async (req, res) => {
  const dialStatus   = req.body.DialCallStatus;
  const businessName = decodeURIComponent(req.query.business || "the business");
  const leadPhone    = decodeURIComponent(req.query.phone || "");
  const host         = req.get("host");

  if (dialStatus !== "completed") {
    const fallbackText = "oh gosh I'm so sorry, our specialist just stepped away for a second. hey could I schedule a quick callback for you? what time works best?";
    const audioUrl     = await sarahSpeak(fallbackText, host);
    return res.type("text/xml").send(`<?xml version="1.0" encoding="UTF-8"?>
<Response>
  ${audioUrl ? `<Play>${audioUrl}</Play>` : `<Say voice="Polly.Joanna-Neural">I'm so sorry, can I schedule a callback?</Say>`}
  <Gather input="speech" timeout="8" speechTimeout="3" action="/voice/book-fallback?business=${encodeURIComponent(businessName)}&phone=${encodeURIComponent(leadPhone)}" method="POST">
    <Say> </Say>
  </Gather>
  <Say voice="Polly.Joanna-Neural">No worries, we will follow up with you soon. Have a great day!</Say>
  <Hangup/>
</Response>`);
  }
  res.type("text/xml").send(`<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>`);
});

app.post("/voice/book-fallback", async (req, res) => {
  const businessName  = decodeURIComponent(req.query.business || "the business");
  const leadPhone     = decodeURIComponent(req.query.phone || "");
  const requestedTime = req.body.SpeechResult || "as soon as possible";
  const { name: repName, phone: repPhone } = getNextTransfer();
  const host = req.get("host");

  const callbacks = readJson(FILES.callbacks, []);
  callbacks.push({ id: uuidv4(), businessName, phone: leadPhone, requestedTime, repName, createdAt: new Date().toISOString() });
  writeJson(FILES.callbacks, callbacks);

  try {
    await twilioClient.messages.create({
      body: `📅 MISSED TRANSFER — Callback booked!\n\nBusiness: ${businessName}\n📞 ${leadPhone}\nRequested: "${requestedTime}"\nAssigned to: ${repName}`,
      from: CONFIG.twilioPhone, to: repPhone,
    });
    await twilioClient.messages.create({
      body: `hey! Sarah from RLS Web Design — our specialist will call you back ${requestedTime} to walk you through your free website demo. talk soon!`,
      from: CONFIG.twilioPhone, to: leadPhone,
    });
  } catch {}

  const confirmText = `perfect! I've got you scheduled and I'm texting you a confirmation right now. our specialist will call you back ${requestedTime}. have a great day!`;
  const audioUrl    = await sarahSpeak(confirmText, host);
  res.type("text/xml").send(`<?xml version="1.0" encoding="UTF-8"?>
<Response>
  ${audioUrl ? `<Play>${audioUrl}</Play>` : `<Say voice="Polly.Joanna-Neural">Perfect, you are scheduled. Have a great day!</Say>`}
  <Hangup/>
</Response>`);
});

app.post("/voice/status", async (req, res) => {
  const { CallSid, CallStatus, Duration } = req.body;
  const queueId  = req.query.queueId;
  const protocol = req.headers["x-forwarded-proto"] || "https";
  const host     = req.get("host");

  log.info("Call status", { CallSid, CallStatus, Duration });

  const stats = getStats();
  if (CallStatus === "no-answer" || CallStatus === "busy") stats.noAnswers++;
  saveStats(stats);

  if (["completed","failed","busy","no-answer","canceled"].includes(CallStatus)) {
    const call = activeCalls[CallSid];
    if (call) {
      saveTranscript({
        id: uuidv4(), businessName: call.businessName,
        outcome: CallStatus, duration: Duration || "0",
        transcript: call.transcript || [], createdAt: new Date().toISOString(),
      });
      delete activeCalls[CallSid];
    }

    if (queueId) {
      const queue = getQueue();
      const item  = queue.items.find(i => i.id === queueId);
      if (item) {
        item.status      = ["failed","busy","no-answer","canceled"].includes(CallStatus) ? CallStatus : "completed";
        item.completedAt = new Date().toISOString();
        item.duration    = Duration;
        queue.currentIndex++;
        saveQueue(queue);
      }
      queueProcessing = false;
      setTimeout(() => processNextInQueue(host, protocol), 5000);
    }
  }
  res.sendStatus(200);
});

// ─── API Routes ───────────────────────────────────────────────────────────────

app.post("/api/call", async (req, res) => {
  if (!isSarahEnabled()) return res.status(403).json({ error: "Sarah is disabled" });
  const { phone, businessName } = req.body;
  if (!phone || !businessName) return res.status(400).json({ error: "phone and businessName required" });
  try {
    const protocol = req.headers["x-forwarded-proto"] || "https";
    const call = await twilioClient.calls.create({
      to: phone, from: CONFIG.twilioPhone,
      url: `${protocol}://${req.get("host")}/voice/start?business=${encodeURIComponent(businessName)}`,
      statusCallback: `${protocol}://${req.get("host")}/voice/status`,
      statusCallbackMethod: "POST", timeout: 30,
      machineDetection: "DetectMessageEnd",
      asyncAmdStatusCallback: `${protocol}://${req.get("host")}/voice/amd?business=${encodeURIComponent(businessName)}`,
    });
    res.json({ success: true, callSid: call.sid });
  } catch (err) { res.status(500).json({ error: err.message }); }
});

app.post("/api/queue/add", (req, res) => {
  const { leads } = req.body;
  if (!leads?.length) return res.status(400).json({ error: "leads array required" });
  const queue = getQueue();
  const items = leads.map(l => ({ id: uuidv4(), name: l.name || "Unknown", phone: l.phone, status: "pending", addedAt: new Date().toISOString() }));
  queue.items.push(...items);
  saveQueue(queue);
  res.json({ success: true, added: items.length, total: queue.items.length });
});

app.post("/api/queue/start", (req, res) => {
  if (!isSarahEnabled()) return res.status(403).json({ error: "Sarah is disabled" });
  const queue    = getQueue();
  const protocol = req.headers["x-forwarded-proto"] || "https";
  if (!queue.items.filter(i => i.status === "pending").length) return res.status(400).json({ error: "No pending items" });
  queue.active = true; queue.paused = false;
  saveQueue(queue);
  processNextInQueue(req.get("host"), protocol);
  res.json({ success: true });
});

app.post("/api/queue/pause",  (req, res) => { const q = getQueue(); q.paused = true;  saveQueue(q); res.json({ success: true }); });
app.post("/api/queue/resume", (req, res) => { const q = getQueue(); q.paused = false; saveQueue(q); processNextInQueue(req.get("host"), req.headers["x-forwarded-proto"] || "https"); res.json({ success: true }); });
app.post("/api/queue/clear",  (req, res) => { writeJson(FILES.queue, { items: [], active: false, currentIndex: 0, paused: false }); queueProcessing = false; res.json({ success: true }); });
app.get("/api/queue", (req, res) => {
  const q = getQueue();
  res.json({ ...q, pending: q.items.filter(i=>i.status==="pending").length, calling: q.items.filter(i=>i.status==="calling").length, completed: q.items.filter(i=>i.status==="completed").length, failed: q.items.filter(i=>["failed","busy","no-answer","canceled"].includes(i.status)).length });
});

app.post("/api/sarah/enable",  (req, res) => { const s = getSystem(); s.sarahEnabled = true;  saveSystem(s); res.json({ success: true, enabled: true  }); });
app.post("/api/sarah/disable", (req, res) => { const s = getSystem(); s.sarahEnabled = false; saveSystem(s); res.json({ success: true, enabled: false }); });
app.get("/api/sarah/status",   (req, res) => res.json(getSystem()));

app.post("/api/training/add", async (req, res) => {
  const { url } = req.body;
  if (!url) return res.status(400).json({ error: "YouTube URL required" });
  try {
    const videoInfo  = await fetchYouTubeInfo(url);
    const techniques = await extractTechniques(videoInfo);
    const training   = getTraining();
    training.videos.push({ ...videoInfo, addedAt: new Date().toISOString(), techniques });
    training.techniques = [...new Set([...techniques, ...training.techniques])].slice(0, 30);
    training.lastUpdated = new Date().toISOString();
    saveTraining(training);
    res.json({ success: true, title: videoInfo.title, techniques });
  } catch (err) { res.status(500).json({ error: err.message }); }
});

app.get("/api/training",    (req, res) => res.json(getTraining()));
app.get("/api/stats",       (req, res) => res.json(getStats()));
app.get("/api/transcripts", (req, res) => res.json(readJson(FILES.transcripts, []).slice(0, 50)));
app.get("/api/learnings",   (req, res) => res.json(getLearnings()));
app.get("/api/callbacks",   (req, res) => res.json(readJson(FILES.callbacks, [])));
app.post("/api/test-texter", async (req, res) => {
  try { await runFollowUpTexter(); res.json({ success: true }); }
  catch (err) { res.status(500).json({ error: err.message }); }
});
app.get("/api/leads", async (req, res) => {
  const leads = await getTodaysFollowUps();
  res.json({ count: leads.length, leads });
});
app.get("/api/logs", (req, res) => {
  res.json(readJson(path.join(CONFIG.dataDir, "logs.json"), []));
});

// ─── Dashboard ────────────────────────────────────────────────────────────────

app.get("/", (req, res) => {
  const html = fs.existsSync(path.join(__dirname, "public", "index.html"))
    ? fs.readFileSync(path.join(__dirname, "public", "index.html"), "utf8")
    : "<h1>RLS Automation Running</h1>";
  res.send(html);
});

app.listen(CONFIG.port, () => log.info("RLS Automation running", { port: CONFIG.port }));
