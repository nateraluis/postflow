# GitHub-Style Posting Calendar - Implementation Plan

## 🎯 Goal
Create a reusable posting calendar component that shows posting activity as a GitHub-style contribution heatmap, with hover tooltips showing daily details.

## 📐 Design System Adherence
- **Colors**: Use PostFlow's existing color scheme
  - Violet accent: `violet-600` (#8b5cf6) for primary actions
  - Amber: `amber-500` (#f59e0b) for highlights
  - Gray scale: `gray-50` to `gray-900` for UI
  - Intensity heatmap: 5 levels from `gray-100` (no posts) to `violet-600` (high activity)
- **Typography**: Tailwind font classes (text-sm, font-medium, etc.)
- **Shadows**: Consistent with existing cards (`shadow`, `rounded-lg`)
- **Interactive elements**: Hover states with `hover:` utilities

## 🏗️ Architecture

### 1. Backend Components

#### **A. Utility Function: `analytics/utils.py`**
Location: `/Users/luisnatera/Documents/tynstudio/postflow/analytics/utils.py`

Create new function: `get_posting_calendar_data(user, platform=None, days=365)`

**Purpose**: Aggregate posting data across all platforms or for a specific platform

**Returns**:
```python
{
    'calendar_data': [
        {
            'date': '2026-01-15',  # ISO date string
            'post_count': 3,
            'total_engagement': 145,
            'posts': [
                {
                    'id': 123,
                    'platform': 'pixelfed',  # or 'mastodon', 'instagram'
                    'platform_name': 'Pixelfed',
                    'content_preview': 'First 50 chars...',
                    'engagement': 85,
                    'url': 'https://...',
                },
                # ... more posts
            ]
        },
        # ... more days
    ],
    'summary': {
        'total_days': 365,
        'days_with_posts': 127,
        'total_posts': 245,
        'current_streak': 7,
        'longest_streak': 21,
        'avg_posts_per_day': 0.67,
        'busiest_day': {'date': '2026-01-20', 'post_count': 5},
    },
    'intensity_levels': {
        'level_0': 0,      # No posts
        'level_1': 1,      # 1 post
        'level_2': 2,      # 2 posts
        'level_3': 3,      # 3-4 posts
        'level_4': 5,      # 5+ posts
    }
}
```

**Data Sources**:
- Pixelfed: `PixelfedPost.posted_at`, aggregate engagement from `PixelfedEngagementSummary`
- Mastodon: `MastodonPost.posted_at`, aggregate from `MastodonEngagementSummary`
- Instagram: `InstagramPost.timestamp`, aggregate from `InstagramEngagementSummary`

**Aggregation Logic**:
1. Query all posts for user across platforms (or specific platform)
2. Filter by date range (default last 365 days)
3. Group by date (truncate to day)
4. Calculate metrics per day
5. Calculate streaks (consecutive days with posts)
6. Determine intensity levels based on post count distribution

#### **B. View Updates**

**Files to modify**:
- `/Users/luisnatera/Documents/tynstudio/postflow/analytics/views.py` - Add to overview dashboard
- `/Users/luisnatera/Documents/tynstudio/postflow/analytics_pixelfed/views.py` - Add to Pixelfed dashboard
- `/Users/luisnatera/Documents/tynstudio/postflow/analytics_mastodon/views.py` - Add to Mastodon dashboard
- `/Users/luisnatera/Documents/tynstudio/postflow/analytics_instagram/views.py` - Add to Instagram dashboard

**Changes**:
Add calendar data to context in each dashboard view:
```python
from analytics.utils import get_posting_calendar_data

# In overview dashboard (all platforms)
calendar_data = get_posting_calendar_data(request.user, platform=None)

# In platform-specific dashboard
calendar_data = get_posting_calendar_data(request.user, platform='pixelfed')

context.update({
    'calendar_data': calendar_data,
})
```

### 2. Frontend Components

#### **A. Reusable Template Partial**
Location: `/Users/luisnatera/Documents/tynstudio/postflow/analytics/templates/analytics/shared/partials/posting_calendar.html`

**Props (context variables)**:
- `calendar_data` - Full calendar data dictionary
- `title` - Optional custom title (default: "Posting Activity")
- `show_summary` - Boolean to show/hide summary stats (default: true)
- `height` - Optional height class (default: auto)

**Structure**:
```html
{% load analytics_filters %}

<div class="bg-white shadow rounded-lg p-6">
    <!-- Header with title and controls -->
    <div class="flex items-center justify-between mb-6">
        <h2 class="text-lg font-semibold text-gray-900">{{ title|default:"Posting Activity" }}</h2>

        <!-- Date range selector (future enhancement) -->
        <div class="text-sm text-gray-500">
            Last 365 days
        </div>
    </div>

    <!-- Summary Statistics (optional) -->
    {% if show_summary %}
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        <div>
            <p class="text-xs text-gray-500">Total Posts</p>
            <p class="text-xl font-bold text-gray-900">{{ calendar_data.summary.total_posts }}</p>
        </div>
        <div>
            <p class="text-xs text-gray-500">Active Days</p>
            <p class="text-xl font-bold text-gray-900">{{ calendar_data.summary.days_with_posts }}</p>
        </div>
        <div>
            <p class="text-xs text-gray-500">Current Streak</p>
            <p class="text-xl font-bold text-violet-600">{{ calendar_data.summary.current_streak }} days</p>
        </div>
        <div>
            <p class="text-xs text-gray-500">Longest Streak</p>
            <p class="text-xl font-bold text-amber-500">{{ calendar_data.summary.longest_streak }} days</p>
        </div>
    </div>
    {% endif %}

    <!-- Calendar Heatmap -->
    <div id="posting-calendar" class="overflow-x-auto">
        <!-- D3.js will render here -->
    </div>

    <!-- Legend -->
    <div class="flex items-center justify-end mt-4 text-xs text-gray-500">
        <span class="mr-2">Less</span>
        <div class="flex gap-1">
            <div class="w-3 h-3 rounded-sm bg-gray-100 border border-gray-200"></div>
            <div class="w-3 h-3 rounded-sm bg-violet-100"></div>
            <div class="w-3 h-3 rounded-sm bg-violet-300"></div>
            <div class="w-3 h-3 rounded-sm bg-violet-500"></div>
            <div class="w-3 h-3 rounded-sm bg-violet-600"></div>
        </div>
        <span class="ml-2">More</span>
    </div>
</div>

<!-- D3.js Calendar Script -->
<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
(function() {
    const calendarData = {{ calendar_data.calendar_data|safe }};
    const intensityLevels = {{ calendar_data.intensity_levels|safe }};

    // Calendar configuration
    const cellSize = 12;
    const cellPadding = 2;
    const monthLabelHeight = 20;
    const dayLabelWidth = 30;

    // Color scale (PostFlow violet palette)
    const colorScale = {
        0: '#f3f4f6',  // gray-100
        1: '#e9d5ff',  // violet-200
        2: '#c4b5fd',  // violet-300
        3: '#a78bfa',  // violet-400
        4: '#8b5cf6',  // violet-600
    };

    // Get intensity level for a post count
    function getIntensityLevel(postCount) {
        if (postCount === 0) return 0;
        if (postCount === 1) return 1;
        if (postCount === 2) return 2;
        if (postCount <= 4) return 3;
        return 4;
    }

    // Create tooltip
    const tooltip = d3.select('body').append('div')
        .attr('class', 'calendar-tooltip')
        .style('position', 'absolute')
        .style('visibility', 'hidden')
        .style('background-color', 'rgba(17, 24, 39, 0.95)')
        .style('color', 'white')
        .style('padding', '12px 16px')
        .style('border-radius', '8px')
        .style('font-size', '0.875rem')
        .style('pointer-events', 'none')
        .style('z-index', '1000')
        .style('box-shadow', '0 4px 6px -1px rgba(0, 0, 0, 0.1)')
        .style('max-width', '300px');

    // Render calendar
    // ... (D3.js implementation details below)
})();
</script>
```

#### **B. D3.js Heatmap Implementation Details**

**Grid Structure**:
- 7 rows (Sunday to Saturday)
- ~52 columns (weeks in a year)
- Cells: 12x12px with 2px padding
- Month labels at top
- Day labels on left (Sun, Mon, etc.)

**Interaction**:
- Hover: Show tooltip with:
  - Date (formatted: "Monday, January 15, 2026")
  - Post count: "3 posts"
  - Total engagement: "145 interactions"
  - List of posts with previews (max 5, show "and X more")
  - Platform badges for each post
- Click: Optional - navigate to day's posts (future enhancement)

**Tooltip Content Example**:
```
Monday, January 15, 2026
────────────────────────
3 posts • 145 interactions

[Pixelfed] "Beautiful sunset today..."
❤️ 45  💬 8  🔁 12

[Mastodon] "Thinking about..."
⭐ 23  💬 5  🔁 3

[Instagram] "New product launch..."
❤️ 52  💬 7  📥 4
```

### 3. Template Integration

#### **A. Analytics Overview Dashboard**
File: `/Users/luisnatera/Documents/tynstudio/postflow/analytics/templates/analytics/dashboard.html`

**Placement**: After header, before platform comparison section (line ~12)

```html
<div class="max-w-4xl mx-auto">
    <h1 class="text-3xl font-bold text-gray-900 mb-2">Analytics Dashboard</h1>
    <p class="text-gray-600 mb-8">View engagement metrics for your social media posts</p>

    <!-- NEW: Posting Calendar -->
    {% if has_pixelfed or has_mastodon or has_instagram %}
        {% include 'analytics/shared/partials/posting_calendar.html' with calendar_data=calendar_data title="Posting Activity (All Platforms)" show_summary=True %}
        <div class="mb-8"></div>
    {% endif %}

    <!-- Platform Comparison Section -->
    {% include 'analytics/shared/partials/platform_comparison.html' %}

    <!-- Rest of dashboard... -->
```

#### **B. Platform-Specific Dashboards**
File: `/Users/luisnatera/Documents/tynstudio/postflow/analytics/templates/analytics/platform_dashboard_content.html`

**Placement**: After header, before stats grid (line ~28)

```html
{% if user_accounts|length > 0 %}
    <!-- NEW: Posting Calendar -->
    {% include 'analytics/shared/partials/posting_calendar.html' with calendar_data=calendar_data title=platform_name|add:" Posting Activity" show_summary=True %}
    <div class="mb-8"></div>

    <!-- Summary Statistics -->
    <div id="stats-container" ...>
```

### 4. Styling Considerations

**Responsive Design**:
- Desktop: Full calendar visible, horizontal scroll if needed
- Tablet: Scaled down cells (10x10px)
- Mobile: Horizontal scroll with sticky day labels

**Colors (PostFlow Design System)**:
- Background: `bg-white` with `shadow` and `rounded-lg`
- Headers: `text-gray-900`, `font-semibold`
- Subtext: `text-gray-500` or `text-gray-600`
- Accent: `violet-600` for streaks, `amber-500` for highlights
- Heatmap: `gray-100` → `violet-100` → `violet-300` → `violet-500` → `violet-600`

### 5. Performance Optimization

**Caching Strategy**:
- Cache calendar data for 1 hour per user
- Invalidate on new post creation
- Use Django's cache framework

**Query Optimization**:
- Use `select_related()` and `prefetch_related()` for post queries
- Aggregate in database, not Python
- Limit to 365 days by default

**Frontend Optimization**:
- Lazy load D3.js if not on page
- Use SVG for calendar (better performance than HTML)
- Debounce tooltip updates

## 📋 Implementation Checklist

### Phase 1: Backend Foundation
- [ ] Create `get_posting_calendar_data()` function in `analytics/utils.py`
- [ ] Add helper functions for streak calculation
- [ ] Add helper functions for intensity level calculation
- [ ] Write tests for calendar data aggregation

### Phase 2: Template Component
- [ ] Create `posting_calendar.html` partial template
- [ ] Implement D3.js calendar rendering
- [ ] Add tooltip with hover behavior
- [ ] Add legend and summary stats
- [ ] Test responsive behavior

### Phase 3: Integration
- [ ] Update `analytics/views.py` for overview dashboard
- [ ] Update `analytics_pixelfed/views.py`
- [ ] Update `analytics_mastodon/views.py`
- [ ] Update `analytics_instagram/views.py`
- [ ] Integrate calendar into all dashboard templates

### Phase 4: Polish
- [ ] Add loading states
- [ ] Handle empty state (no posts)
- [ ] Add error handling
- [ ] Optimize queries and caching
- [ ] Test with various data volumes
- [ ] Mobile/responsive testing

### Phase 5: Future Enhancements (Optional)
- [ ] Date range selector (30/90/180/365 days)
- [ ] Click to navigate to day's posts
- [ ] Export calendar data
- [ ] Customizable intensity thresholds
- [ ] Comparison mode (year over year)

## 🧪 Testing Scenarios

1. **No posts**: Show empty calendar with zero stats
2. **Sparse posting**: Few posts spread across year
3. **Consistent posting**: Daily or near-daily posting
4. **Heavy posting**: Multiple posts per day
5. **Multi-platform**: Posts from all three platforms on same days
6. **Platform-specific**: Filter to single platform
7. **Edge cases**: Leap years, timezone boundaries, year transitions

## 📈 Success Metrics

- Calendar loads in < 500ms with 365 days of data
- Tooltip appears within 100ms of hover
- Responsive on all screen sizes (mobile, tablet, desktop)
- Visually consistent with PostFlow design system
- Reusable across all analytics pages
- Accurate streak and statistics calculations
