# PostFlow TODO

## Analytics Improvements

### UI/UX Enhancements

- [ ] **Add posting consistency metrics**
  - Create GitHub-style commit calendar visualization
  - Show posting frequency over time (daily/weekly/monthly)
  - Display average engagement per time period
  - Highlight most active posting days/times
  - Calculate consistency score (regularity of posting)
  - Related: Create new view/template for consistency dashboard

## Technical Notes

- All analytics features are in the `analytics_pixelfed/` app
- Consider caching for expensive aggregation queries
- Test with accounts that have large numbers of posts (>1000)

### Pixelfed/Mastodon API Limitations

**Timestamp Availability:**
- ✅ **Post timestamps**: Available via `created_at` and `edited_at` fields in Status object
- ✅ **Comment timestamps**: Available via `created_at` field in Status object (comments are statuses)
- ❌ **Like timestamps**: NOT available - `/api/v1/statuses/:id/favourited_by` only returns Account objects
- ❌ **Share timestamps**: NOT available - `/api/v1/statuses/:id/reblogged_by` only returns Account objects

**Workaround Implemented:**
- Added `first_seen_at` field to PixelfedLike and PixelfedShare models
- Uses `timezone.now()` when first discovering a like/share
- Provides estimated timeline of engagement (better than nothing)
- More frequent fetching = more accurate timeline estimates

**Available Metrics:**
- ✅ Aggregate counts: `replies_count`, `reblogs_count`, `favourites_count` from Status object
- ✅ Post metadata: visibility, language, sensitive flags, spoiler text
- ✅ Threading information: reply chains and parent post references
- ✅ Edit history: `edited_at` timestamp when posts are modified
- ❌ Impressions/views: Not supported by Mastodon API
- ❌ Engagement rate: Cannot calculate without impression data
