# PostFlow Marketing Specialist Agent

This document explains how to use the Marketing Specialist agent for PostFlow marketing content creation.

## Overview

The Marketing Specialist is a custom Claude Code agent specialized in creating compelling marketing copy for PostFlow. The agent has deep knowledge of:

- PostFlow's features, pricing, and technical capabilities
- Target audience (photographers and visual creators)
- Unique selling points vs. competitors
- Brand voice and messaging guidelines
- Conversion optimization best practices

## Quick Start

### Using the Agent

You can invoke the marketing specialist agent using the Task tool in Claude Code:

```
"Use the marketing-specialist agent to create [your marketing task]"
```

### Example Invocations

**Landing Page Copy:**
```
Use the marketing-specialist agent to create a hero section for the landing page
emphasizing our Mastodon and Pixelfed support as a unique differentiator.
```

**Email Campaign:**
```
Use the marketing-specialist agent to write a welcome email sequence for new
users who just signed up. Include quick wins and feature highlights.
```

**Social Media Content:**
```
Use the marketing-specialist agent to create 5 Instagram posts targeting
photographers concerned about AI training on their images.
```

**Ad Copy:**
```
Use the marketing-specialist agent to write Google PPC ad copy targeting
"social media scheduling for photographers" with a $10/month pricing angle.
```

**Blog Posts:**
```
Use the marketing-specialist agent to suggest 10 blog post topics that would
drive SEO traffic from photography-related keywords.
```

**Conversion Optimization:**
```
Use the marketing-specialist agent to review our pricing page CTA and suggest
improvements to increase conversion rates.
```

## What the Agent Knows

### Product Knowledge
- All PostFlow features (multi-platform posting, hashtag management, calendar view, etc.)
- Pricing ($10/month, $100/year)
- Supported platforms (Instagram, Pixelfed, Mastodon)
- Privacy commitment (no AI training on images)
- Technical architecture (Django, S3 storage, timezone handling)

### Target Audience
- **Primary:** Professional and semi-professional photographers
- **Pain Points:** Time-consuming manual posting, AI training concerns, platform dependency
- **Motivations:** Efficiency, privacy, creative control, affordability
- **Platforms:** Active on Instagram, exploring Mastodon/Pixelfed alternatives

### Competitive Positioning
- **vs. Buffer/Hootsuite:** Purpose-built for photographers, 1/3 the price, Mastodon support
- **vs. Later/Planoly:** Multi-platform beyond Meta, privacy-first, decentralized networks
- **vs. Manual Posting:** Time savings, consistency, professional workflow

### Brand Voice
- **Tone:** Professional yet approachable, empowering, creator-focused
- **Core Messages:** Efficiency, multi-platform, privacy, creator-centric, simplicity
- **Avoid:** Corporate jargon, overpromising, fear-mongering

## Content Types the Agent Can Create

### 1. Website Copy
- Hero sections and headlines
- Feature descriptions
- About page content
- FAQ content
- Pricing page copy
- CTAs and microcopy

### 2. Email Marketing
- Welcome sequences
- Feature announcements
- Re-engagement campaigns
- Newsletter content
- Promotional emails
- Transactional email copy

### 3. Social Media
- Instagram posts and captions
- Mastodon/Pixelfed content
- Twitter/X posts
- Social media ad copy
- Hashtag strategies

### 4. Advertising
- Google PPC ads
- Facebook/Instagram ads
- Display ad copy
- Retargeting campaigns

### 5. Content Marketing
- Blog post topics and outlines
- SEO-optimized articles
- Guest post pitches
- Case studies
- Tutorials and guides

### 6. Strategy & Analysis
- Audience segmentation
- Campaign planning
- Competitive analysis
- A/B testing recommendations
- Content calendars

## Best Practices for Working with the Agent

### 1. Provide Clear Context
When invoking the agent, include:
- **Goal:** What you're trying to achieve
- **Audience:** Which persona you're targeting
- **Channel:** Where the content will appear
- **Constraints:** Character limits, deadlines, brand guidelines
- **Tone:** Preferred messaging style

**Example:**
```
Use the marketing-specialist agent to create an Instagram ad targeting busy
professional photographers who struggle to find time for social media.
The ad should emphasize time savings and be under 125 characters for the
primary text. Use an empowering, practical tone.
```

### 2. Specify Deliverables
Be explicit about what format you need:
- "Create 3 headline variations for A/B testing"
- "Write a complete email with subject line, preview text, and body"
- "Suggest 5 blog post titles with SEO keywords identified"

### 3. Iterate and Refine
The agent can refine its output based on feedback:
```
Use the marketing-specialist agent to make the headline more benefit-driven
and less feature-focused. Target photographers who value privacy.
```

### 4. Leverage Product Knowledge
Ask the agent questions about positioning:
```
Use the marketing-specialist agent to explain how we should position our
Mastodon support compared to competitors who only support Instagram.
```

## Example Workflows

### Creating a Landing Page Section

**Step 1: Initial Creation**
```
Use the marketing-specialist agent to create a features section for the
landing page highlighting our hashtag management, multi-platform posting,
and calendar view features. Target busy photographers.
```

**Step 2: Refinement**
```
Use the marketing-specialist agent to make the features section more
scannable with shorter paragraphs and bullet points.
```

**Step 3: CTA Optimization**
```
Use the marketing-specialist agent to create 5 CTA button text variations
for the features section that emphasize trying the product.
```

### Planning an Email Campaign

**Step 1: Strategy**
```
Use the marketing-specialist agent to outline a 3-email welcome sequence
for new users who just signed up but haven't connected their first account.
```

**Step 2: Execution**
```
Use the marketing-specialist agent to write Email 1 of the welcome sequence
with subject line, preview text, and body copy focused on the quick win of
connecting their first social media account.
```

**Step 3: Testing**
```
Use the marketing-specialist agent to create A/B test variations for the
subject line of Email 1, one emphasizing curiosity and one emphasizing benefit.
```

## Marketing Personas & Messaging

The agent understands four core personas:

### 1. Busy Professional Photographer
- **Pain:** No time between shoots and editing to manage multiple social accounts
- **Message:** Automate posting workflow, schedule a week of content in 30 minutes
- **CTA:** "Start Saving Time Today"

### 2. Privacy-Conscious Creator
- **Pain:** Distrust of Meta/Instagram, concern about AI training on their work
- **Message:** Your photos, your data. No AI training. Post to Mastodon and Pixelfed.
- **CTA:** "Take Control of Your Content"

### 3. Multi-Platform Content Creator
- **Pain:** Manually posting same content to multiple platforms wastes time
- **Message:** Post once, reach everywhere. Cross-post in one workflow.
- **CTA:** "Simplify Your Workflow"

### 4. Budget-Conscious Freelancer
- **Pain:** Enterprise tools cost $15-30/month for features they don't need
- **Message:** Professional scheduling at $10/month. All features included.
- **CTA:** "See Pricing"

## Advanced Usage

### Campaign Planning
```
Use the marketing-specialist agent to create a content calendar for Q1 2025
including blog posts, email campaigns, and social media themes aligned with
photographer pain points and seasonal trends.
```

### Competitive Analysis
```
Use the marketing-specialist agent to analyze how we should respond to Buffer's
new pricing changes. Suggest messaging that highlights our advantages without
directly attacking competitors.
```

### Conversion Funnel Optimization
```
Use the marketing-specialist agent to map out content needs for each stage of
our conversion funnel (awareness → consideration → decision → retention) and
suggest 3 pieces of content for each stage.
```

### SEO Strategy
```
Use the marketing-specialist agent to identify 20 high-value keywords for the
photographer audience and suggest blog post topics that could rank for those terms.
```

## Tips for Maximum Effectiveness

1. **Be Specific:** "Create an email" vs. "Create a re-engagement email for users who haven't logged in for 30 days targeting the privacy-conscious persona"

2. **Use Personas:** Reference the four core personas by name to get targeted messaging

3. **Specify Constraints:** Include character limits, tone preferences, and brand guidelines

4. **Request Variations:** Ask for multiple options for A/B testing (headlines, CTAs, subject lines)

5. **Iterate:** Don't accept the first draft—refine based on your needs and brand voice

6. **Combine with Code:** Use the agent for copy, then implement it yourself in templates with Django/Tailwind

## File Location

The agent configuration is stored at:
```
.claude/agents/marketing-specialist.md
```

To modify the agent's knowledge or capabilities, edit this file and update:
- Product knowledge in the "Deep Product Knowledge" section
- Messaging guidelines in the "Brand Voice & Messaging" section
- Personas in the "Persona-Specific Messaging" section
- Examples in the "Example Marketing Copy Styles" section

## Integration with PostFlow Development

### Using Marketing Copy in Templates

After generating copy with the agent, integrate it into Django templates:

**Example: Hero Section**
```html
<!-- postflow/templates/postflow/components/hero.html -->
<div class="hero-section">
    <h1>{{ headline_from_agent }}</h1>
    <p>{{ subheadline_from_agent }}</p>
    <a href="{% url 'register' %}" class="cta-button">
        {{ cta_text_from_agent }}
    </a>
</div>
```

### Testing Copy Variations

Use Django's template system to A/B test variations:
```python
# In views.py
import random

def landing_page(request):
    headlines = [
        "Automate Your Photography Sharing Workflow",
        "Post Once, Reach Photographers Everywhere",
        "Reclaim Your Time from Social Media"
    ]
    context = {
        'headline': random.choice(headlines)
    }
    return render(request, 'landing.html', context)
```

### Email Campaign Implementation

After generating email copy, implement with Django's email system:
```python
from django.core.mail import send_mail
from django.template.loader import render_to_string

def send_welcome_email(user):
    subject = "Welcome to PostFlow - Your First Steps"  # From agent
    message = render_to_string('emails/welcome.html', {
        'user': user,
        'cta_url': 'https://postflow.app/connect-account'
    })
    send_mail(subject, message, 'hello@postflow.app', [user.email])
```

## Troubleshooting

### Agent Not Responding as Expected

**Issue:** Copy is too generic or doesn't match PostFlow's voice
**Solution:** Provide more context about the specific persona and channel. Reference the brand voice section explicitly.

**Issue:** Agent lacks updated product information
**Solution:** Edit `.claude/agents/marketing-specialist.md` to update the product knowledge section with new features or pricing.

**Issue:** Copy is too long/short
**Solution:** Specify character or word count constraints in your invocation.

### Best Practices Reminders

- Always specify the target persona (busy pro, privacy-conscious, multi-platform, budget-conscious)
- Include the channel context (email, landing page, ad, social media)
- Request multiple variations for important copy (headlines, CTAs, subject lines)
- Iterate based on brand voice and conversion goals
- Test copy variations with real users before committing

## Support & Feedback

To improve the marketing agent:
1. Edit `.claude/agents/marketing-specialist.md` with new product knowledge
2. Add new personas or messaging angles as they develop
3. Update competitive positioning as the market changes
4. Include successful copy examples to guide future outputs

---

**Quick Reference:**

- **Agent Name:** `marketing-specialist`
- **File Location:** `.claude/agents/marketing-specialist.md`
- **Invocation:** Use the Task tool with the agent name
- **Primary Use Cases:** Landing pages, emails, ads, social media, blog posts, strategy
- **Target Audience:** Photographers and visual creators
- **Brand Voice:** Professional, empowering, creator-focused
