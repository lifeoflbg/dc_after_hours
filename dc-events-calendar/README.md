# 🏛️ DC Cultural & Policy Events Calendar

A self-hosted, auto-updating events aggregator for Washington DC's think tanks, museums, cultural centers, and embassies. Hosted **100% free** on GitHub Pages, refreshed every 6 hours via GitHub Actions.

**Live site** → `https://YOUR-USERNAME.github.io/YOUR-REPO/`  
**iCal feed** → `https://YOUR-USERNAME.github.io/YOUR-REPO/events.ics`

---

## 📋 Sources (16 institutions)

| Category | Sources |
|---|---|
| 🔵 Think Tanks | Brookings Institution, CATO Institute, Heritage Foundation, Council on Foreign Relations |
| 🟠 Smithsonian | Smithsonian Institution (si.edu/events + Natural History Museum) |
| 🟣 Shakespeare | Folger Shakespeare Library (all programs, theater, exhibitions) |
| 🟢 Cultural Centers | Kennedy Center, National Gallery of Art, Library of Congress, Mexican Cultural Institute, Alliance Française DC, Italian Cultural Institute, Korean Cultural Center, Goethe-Institut Washington |
| 🩷 Embassies | Embassy Events via Eventbrite DC, Passport DC (Events DC) |

---

## 🚀 One-Time Setup (10 minutes)

### Step 1 — Create your GitHub repository

1. Go to [github.com/new](https://github.com/new)
2. Create a **public** repository (e.g. `dc-events-calendar`)
3. Clone it and copy all files from this project:
   ```bash
   git clone https://github.com/YOUR-USERNAME/dc-events-calendar.git
   cd dc-events-calendar
   # copy all project files here
   git add .
   git commit -m "Initial setup"
   git push origin main
   ```

### Step 2 — Enable GitHub Pages

1. Go to your repo → **Settings** → **Pages**
2. Under **Source**, select **GitHub Actions**
3. That's it — the workflow handles deployment automatically

> **Note:** The workflow uses the `actions/deploy-pages` action, which requires "Source: GitHub Actions" (not the branch/folder option).

### Step 3 — Trigger the first scrape

Either push a commit (the workflow runs on every push to `main`) or:

1. Go to **Actions** tab in your repo
2. Click **Scrape DC Events & Publish Calendar**
3. Click **Run workflow** → **Run workflow**

The site will be live at `https://YOUR-USERNAME.github.io/dc-events-calendar/` within a few minutes.

---

## 📅 Subscribing to the Calendar

### Google Calendar
1. On the left sidebar, click **+** next to "Other calendars"
2. Select "From URL"
3. Paste: `https://YOUR-USERNAME.github.io/dc-events-calendar/events.ics`

### Apple Calendar
1. **File** → **New Calendar Subscription**
2. Paste the iCal URL
3. Set auto-refresh to "Every hour" or "Every day"

### Outlook
1. **Add Calendar** → **Subscribe from web**
2. Paste the iCal URL

### Squarespace
1. Add a **Calendar Block** to any page
2. Select **External Calendar** / **iCal Feed**
3. Paste the iCal URL

---

## 🗂️ Project Structure

```
dc-events-calendar/
├── scraper.py                    # All 16 scrapers + iCal/JSON output
├── requirements.txt              # Python deps
├── .github/
│   └── workflows/
│       └── scrape.yml            # Runs scraper + deploys GitHub Pages
└── docs/
    ├── index.html                # The full calendar website
    ├── events.ics                # Generated iCal feed
    └── events.json               # Generated JSON (used by the website)
```

---

## ➕ Adding More Sources

1. Open `scraper.py`
2. Write a new `scrape_SOURCENAME()` function following the existing pattern
3. Add it to the `SCRAPERS` list in `main()`
4. Add the source to `SOURCE_META` dict with its category
5. Add a badge to `docs/index.html` in the sources strip

---

## ⚙️ Schedule

The scraper runs at **00:00, 06:00, 12:00, and 18:00 UTC** daily.

To change: edit `.github/workflows/scrape.yml`:
```yaml
- cron: "0 */6 * * *"    # every 6h (default)
- cron: "0 8 * * *"      # daily at 8am UTC
```

---

## 🐛 Troubleshooting

| Problem | Solution |
|---|---|
| Site shows "run the scraper first" | Go to Actions tab → run the workflow manually |
| No events from a source | Check Actions logs; the site may use JS rendering. Consider Playwright for those sources. |
| GitHub Actions fails | Check the Actions tab → failed run → expand steps for error details |
| iCal doesn't refresh in calendar app | Some apps cache aggressively; set the refresh to 1 hour, or append `?v=2` to bust the cache |

---

## 📜 License

MIT — free to use and modify.
