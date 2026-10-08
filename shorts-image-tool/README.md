# Shorts Image Tool

Give it a text file of search terms, get back folders of high-resolution images
ready to drop into a YouTube Short. Every image also gets a **1080x960 cropped
copy** (the bottom half of a 9:16 Shorts frame) with faces and subjects kept in
frame automatically.

Sources it can pull from:

| Tag at start of line | Where it searches                                    | Good for                                   |
|----------------------|------------------------------------------------------|--------------------------------------------|
| `tmdb:`              | The Movie Database (movie/TV stills, actor photos)   | Shows, films, actors                       |
| `google:`            | Google Images (through SerpAPI)                      | Anything specific: memes, characters, news |
| *(no tag)*           | Unsplash + Pexels + Pixabay                          | Free stock photos, b-roll backgrounds      |
| `unsplash:` `pexels:` `pixabay:` | Just that one stock site                 | When you want a specific site              |

---

## 1. Install (one time, about 5 minutes)

### Step 1: Install Python

Open a terminal and type `python --version` (or `python3 --version` on Mac).
If you see `Python 3.9` or higher, skip ahead. Otherwise:

- **Windows:** download from <https://www.python.org/downloads/>. On the first
  screen of the installer, **tick "Add python.exe to PATH"** before clicking Install.
- **Mac:** download from the same page and run the installer. Afterwards use
  `python3` instead of `python` in the commands below.

### Step 2: Open a terminal in this folder

- **Windows:** open the `shorts-image-tool` folder in File Explorer, click the
  address bar, type `cmd` and press Enter.
- **Mac:** open Terminal, type `cd ` (with a space), drag the
  `shorts-image-tool` folder into the Terminal window, press Enter.

### Step 3: Install the libraries

```
pip install -r requirements.txt
```

(On Mac, `pip3` if `pip` isn't found.) This installs five small libraries.
One of them, OpenCV, powers the face detection. If it refuses to install on your
machine, open `requirements.txt`, delete the `opencv-python-headless` line and run
the command again. The tool still works, it just uses a simpler "busiest part of
the picture" crop instead.

### Step 4: Create your `.env` file

The `.env` file is where your API keys live. It is private and never uploaded
anywhere.

1. In the `shorts-image-tool` folder, make a copy of `.env.example`.
2. Rename the copy to exactly `.env` (nothing before the dot, nothing after `env`).
   - Windows may warn about changing the file type. Say yes.
   - If Windows hides file extensions, the copy may secretly be called
     `.env.txt`. Turn on **View > Show > File name extensions** in File
     Explorer and fix the name.
3. Open `.env` in Notepad / TextEdit and paste each key after its `=` sign.
   No spaces, no quotes.

You don't need all five keys. Any source without a key is simply skipped with a
message. Get the ones you care about using the guide below.

---

## 2. Getting the free API keys

All five are free. Each takes 2 to 5 minutes. You'll need an email address.

### TMDB (movie & TV stills, actor photos)

1. Go to <https://www.themoviedb.org/signup> and create an account. Verify the email.
2. Go to <https://www.themoviedb.org/settings/api> and click **Request an API Key**
   (or "click here" under "Request an API key").
3. Choose **Developer**. Accept the terms.
4. Fill in the form. For "Type of use" pick *Personal*. For the application
   name and summary, anything honest works, e.g. "Image research for my YouTube
   channel". Put `N/A` for the URL if you don't have one.
5. Submit. The key is issued instantly. On the same settings page you'll see
   **API Key** (a 32-character string) and **API Read Access Token** (a very long
   string starting with `eyJ`). Either one works. Copy it into `.env`:

   ```
   TMDB_API_KEY=your_key_here
   ```

Free limit: ~50 requests per second. You will never hit it.

### SerpAPI (Google Images)

1. Go to <https://serpapi.com/users/sign_up> and sign up. Verify the email
   (they may also ask for a phone number to confirm you're human).
2. Go to <https://serpapi.com/manage-api-key>. Your key is shown there.
3. Copy it into `.env`:

   ```
   SERPAPI_API_KEY=your_key_here
   ```

Free limit: **250 searches per month**. Each `google:` line in your keywords file
uses one search, so that's 250 search terms a month.

### Unsplash

1. Go to <https://unsplash.com/join> and create an account.
2. Go to <https://unsplash.com/oauth/applications> and click **New Application**.
3. Tick all the guideline checkboxes and click **Accept terms**.
4. Give it a name and description (e.g. "Shorts image tool", "finds background
   images for my videos"). Click **Create application**.
5. Scroll down on the application page to **Keys**. Copy the **Access Key**
   (not the Secret key) into `.env`:

   ```
   UNSPLASH_ACCESS_KEY=your_key_here
   ```

Free limit: 50 requests per hour. One search term = one request, so up to ~50
terms per hour.

### Pexels

1. Go to <https://www.pexels.com/join/> and create an account.
2. Go to <https://www.pexels.com/api/> and click **Get Started** / **Your API Key**.
3. Fill in the short form (what you'll use it for: "sourcing images for YouTube
   videos") and submit. The key appears on screen.
4. Copy it into `.env`:

   ```
   PEXELS_API_KEY=your_key_here
   ```

Free limit: 200 requests per hour, 20,000 per month.

### Pixabay

1. Go to <https://pixabay.com/accounts/register/> and create an account.
   Verify the email.
2. While logged in, go to <https://pixabay.com/api/docs/>.
3. Scroll down a little to the **Search Images** section. Your personal key is
   printed right there in the grey box next to `key` (it looks like
   `12345678-abcdef...`).
4. Copy it into `.env`:

   ```
   PIXABAY_API_KEY=your_key_here
   ```

Free limit: 100 requests per minute.

---

## 3. Run it

Edit `keywords.txt`. One search term per line:

```
tmdb: Breaking Bad Walter White
tmdb: Bryan Cranston
google: Jim Lahey drunk Trailer Park Boys
city skyline at night
```

Then, in your terminal (in the `shorts-image-tool` folder):

```
python fetch_images.py keywords.txt
```

You'll see progress as it goes:

```
[1/4] Breaking Bad Walter White  (source: tmdb)
  TMDB: 'Breaking Bad Walter White' looks like a TV show: Breaking Bad (matched on 'Breaking Bad')
  TMDB: 24 results
    + 1/8 [tmdb     ] breaking-bad-walter-white_01.jpg (3840x2160, crop: faces)
    + 2/8 [tmdb     ] breaking-bad-walter-white_02.jpg (3840x2160, crop: energy)
    - skip [tmdb     ] near-duplicate
    ...
```

### What you get

```
output/
  breaking-bad-walter-white/
    breaking-bad-walter-white_01.jpg      <- full-size original
    breaking-bad-walter-white_02.jpg
    ...
    cropped/
      breaking-bad-walter-white_01.jpg    <- 1080x960 Shorts crop
      breaking-bad-walter-white_02.jpg
      ...
    sources.csv                           <- where every image came from
  bryan-cranston/
  jim-lahey-drunk-trailer-park-boys/
  city-skyline-at-night/
```

`sources.csv` opens in Excel / Google Sheets and lists, for each image: the
file name, the cropped file name, which site it came from, the page it was on,
the direct image URL, its size, and the photographer / credit. Useful for
attribution and for checking licences.

### Options

```
python fetch_images.py keywords.txt --count 12        # 12 images per term instead of 8
python fetch_images.py keywords.txt --min-width 1200  # be pickier about resolution (default 800)
python fetch_images.py keywords.txt --output D:\clips # save somewhere else
python fetch_images.py keywords.txt --no-crop         # skip the cropped copies
python fetch_images.py keywords.txt --crop-size 1080x1920   # full 9:16 frame instead of bottom half
python fetch_images.py keywords.txt --no-faces        # turn off face detection
python fetch_images.py --help                         # everything
```

### Running it again

Safe to re-run. Images already in a folder are kept, duplicates are skipped,
and numbering continues from where it left off. If a folder already has the
requested number of images, that term is skipped entirely. To start fresh for
a term, just delete its folder.

---

## 4. How it decides what to keep

- **Resolution:** anything narrower than 800px is skipped (change with `--min-width`).
- **Duplicates:** identical files are skipped, and so are near-identical ones
  (the same photo at a different size or compression) using a perceptual hash.
- **Broken links:** 404s, web pages pretending to be images, and corrupt files
  are skipped with a one-line note. The tool keeps going.
- **TMDB:** the term is looked up as a movie, TV show or person. For titles it
  downloads backdrops (widescreen stills, text-free versions first); for people
  it downloads profile photos. If the full term doesn't match (e.g. "Breaking
  Bad Walter White"), it tries shorter versions until something hits ("Breaking
  Bad").
- **Stock (no tag):** results from Unsplash, Pexels and Pixabay are interleaved
  so you get a mix rather than eight from one site.

## 5. How the crop works

The crop is 1080x960: the bottom half of a 1080x1920 Shorts frame, which is
where you'd put the picture under a talking head or a caption.

1. The image is scaled so it fully covers 1080x960.
2. If OpenCV is installed it looks for faces (YuNet detector, downloaded once
   into `models/`, with the classic Haar cascade as backup). If it finds any,
   the crop is positioned so the faces sit in the upper third with the body
   below.
3. Otherwise it finds the "busiest" region of the image (most edges and detail,
   nudged toward the centre) and crops there.
4. If all else fails, a plain centre crop.

The terminal shows which method was used for each image (`crop: faces`,
`crop: energy`, `crop: center`).

---

## 6. Troubleshooting

| Message | What to do |
|---|---|
| `No .env file found` | You haven't made the `.env` file yet, or it is named `.env.txt`. See Install step 4. |
| `TMDB skipped: TMDB_API_KEY is not set` | That key is blank in `.env`. Add it, or ignore if you don't need that source. |
| `rejected the key` / `401` | The key was pasted wrong. Re-copy it with no spaces or quotes. |
| `TMDB: no movie, TV show or person matches` | TMDB doesn't know that title. Check the spelling, or use a `google:` line instead. |
| `SerpAPI monthly search limit reached` | You've used the free 250 searches this month. |
| `Unsplash rate limit hit` | 50 searches/hour on the free tier. Wait an hour. |
| `Only found 3 usable image(s) out of 8 wanted` | The sources didn't have enough large, unique images for that term. Try a broader term or a `google:` version. |
| `Missing dependency` | Run `pip install -r requirements.txt` again. |
| `python` is not recognised | Python isn't on your PATH. Reinstall and tick "Add python.exe to PATH", or use `py` instead of `python` on Windows. |

## 7. A note on licences

- **Unsplash, Pexels, Pixabay** images are free to use commercially without
  attribution (credit is still appreciated; it's in `sources.csv`).
- **TMDB** images are owned by the studios. TMDB allows use for commentary and
  fan content; monetised use is your call to make.
- **Google Images** results can be anything from anywhere. Check the `page_url`
  column in `sources.csv` before using one in a published video.
