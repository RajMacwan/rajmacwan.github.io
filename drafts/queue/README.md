# Weekly grid post queue

`weekly_grid_publisher.py` (run by the **Weekly Grid Post (rotating)** GitHub
Action) publishes one post per week, rotating through five grids:

```
Threat → Infra → Dark → AI → Intel   (each grid every 5 weeks)
```

Tuesdays at 11:00 AM America/New_York, starting 2026-07-14 (week 0 = Threat).

## How to add a post

1. Write the post as a complete blog article (copy any file in `blog/` as a
   template) and save it in the folder for its grid:
   `drafts/queue/<grid>/` where `<grid>` is one of
   `threat`, `infra`, `dark`, `ai`, `intel`.
2. Prefix the filename with a two-digit order number, e.g.
   `03-my-post-slug.html`. Within a grid, drafts publish in filename order
   (lowest first). The `NN-` prefix is **stripped** from the published URL,
   so `03-my-post-slug.html` goes live at `/blog/my-post-slug.html`.
3. Leave two placeholders in the article for the publisher to fill:
   - `__PUBDATE_ISO__` — the publish date (appears in the meta line and the
     `article:published_time` tag).
   - `__READMIN__` — the read-time estimate (computed from word count).
   The grid pill class (`grid-pill-<grid>`) and `<meta name="description">`
   are read from the file to build the listing cards, so set them correctly.

## What happens each week

The publisher promotes the next draft for that week's grid to `blog/`, stamps
the date and read time, inserts cards into the grid landing page and the blog
index, adds a `feed.xml` item and a `sitemap.xml` URL, and rebuilds the
manifest. If a grid's queue is empty on its week, it logs and skips cleanly —
no post that week.

## Testing

Actions tab → **Weekly Grid Post (rotating)** → **Run workflow**, tick
**force** (and optionally set a `publish_date` like `2026-07-14` to target a
specific grid) to publish immediately instead of waiting for Tuesday.
