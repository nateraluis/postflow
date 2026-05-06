# Platform Feature Matrix

Feature support across Instagram, Pixelfed, and Mastodon. Updated as platforms add/remove API capabilities.

## Publishing Features

| Feature | Instagram | Pixelfed | Mastodon |
|---|---|---|---|
| Single image post | Yes | Yes | Yes |
| Carousel (multi-image) | Yes (2-10) | Yes | Yes |
| Video/Reels | Yes (API) | Yes | Yes |
| Stories | Yes (API) | No | No |
| Caption | Yes (2,200 chars) | Yes (500 chars default) | Yes (500 chars default) |
| Hashtags | Yes (5 max, Dec 2025) | Yes (no limit) | Yes (no limit) |
| Alt text on images | Yes | Yes (description) | Yes (description) |
| Alt text on video | No | Yes | Yes |
| Location tagging | Yes (location_id) | No | No |
| User tagging (positional) | Yes (x, y coords) | No | No |
| User tagging (mentions) | Yes (@username in caption) | Yes (@user@instance) | Yes (@user@instance) |
| Collaborators | Yes (max 3, invite required) | No | No |
| Visibility settings | Public only (via API) | Public/Unlisted/Private/Direct | Public/Unlisted/Private/Direct |
| Scheduled publishing | Via PostFlow | Via PostFlow | Via PostFlow |

## Analytics Features

| Feature | Instagram | Pixelfed | Mastodon |
|---|---|---|---|
| Like counts | Yes (Insights API) | Yes (favourites_count) | Yes (favourites_count) |
| Comment counts | Yes (Insights API) | Yes (replies_count) | Yes (replies_count) |
| Share/Repost counts | Yes (Insights API) | Yes (reblogs_count) | Yes (reblogs_count) |
| Impressions/Views | Yes (Insights API) | No | No |
| Reach | Yes (Insights API) | No | No |
| Engagement rate | Yes (calculated) | No (no impressions) | No (no impressions) |
| Like timestamps | No | No (first_seen_at workaround) | No (first_seen_at workaround) |
| Comment timestamps | Yes | Yes (created_at) | Yes (created_at) |
| Commenter usernames | No | Yes | Yes |
| Liker usernames | No | Yes | Yes |
| Reels watch time | Yes (ig_reels_avg_watch_time) | N/A | N/A |
| Reels skip rate | Yes (Insights API) | N/A | N/A |
| Post edit history | No | Yes (edited_at) | Yes (edited_at) |

## API Limitations (Cannot Be Worked Around)

| Limitation | Platform |
|---|---|
| Music/trending audio cannot be added via API | Instagram |
| User tags on Reels not supported via API | Instagram |
| Alt text only on images, not Reels or Stories | Instagram |
| Collaborators must accept invite manually | Instagram |
| Stories cannot contain carousels | Instagram |
| No location tagging equivalent | Pixelfed/Mastodon |
| No collaborator concept (use mentions instead) | Pixelfed/Mastodon |
| No impression/view data | Pixelfed/Mastodon |
| No like/share timestamps (only first_seen_at) | Pixelfed/Mastodon |

## Token Management

| Feature | Instagram | Pixelfed | Mastodon |
|---|---|---|---|
| Token type | Page access token | OAuth bearer | OAuth bearer |
| Token expiration | ~60 days | No expiry | No expiry |
| Auto-refresh | Yes (every 6 hours) | N/A | N/A |
| OAuth flow | Facebook Graph API | Instance OAuth | Instance OAuth |
