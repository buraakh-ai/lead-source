---
name: contact-extraction
description: Extract emails, phone numbers, and LinkedIn URLs from a business webpage's HTML. Prefers schema.org JSON-LD and the page footer over a full-page scan, since those are higher-confidence, targeted sources. Use when you have a page's raw HTML and need structured contact details out of it.
---

# Contact extraction

Given a page's raw HTML and its URL, extract contact details in this priority order:

1. **schema.org JSON-LD** (`<script type="application/ld+json">` blocks) - look for
   `email` and `telephone` fields, including nested `contactPoint`/`@graph` objects.
   This is machine-readable data the site author intentionally published, so treat it
   as highest confidence.
2. **The page footer** (`<footer>` tags, or any element whose `id`/`class` contains
   "footer") - scan for `mailto:`/`tel:` links, LinkedIn URLs, and email/phone regex
   matches in the footer's text. Most small-business sites put their contact block here.
3. **Only if both of the above found nothing**, fall back to scanning the *whole* page's
   links and text with the same regexes. This is noisier (dates, prices, other people's
   numbers quoted in blog posts can all look like phone numbers), so it's a last resort,
   not a first choice.

If a page has no contact details at all, look at `follow_links` (links whose href or
label mentions "contact", "about", or "team") and follow one of them one level deep
before giving up on that page.

A phone-looking match should only count if it has 7-15 digits once punctuation is
stripped - shorter/longer sequences are usually not real phone numbers.

Treat h1/h2/h3 headings with 6 words or fewer as `name_hints` - short headings near
contact info often carry a person's or business's name.

## Scripts

`scripts/extract_contacts.py <url>` fetches the URL and prints the same extraction this
skill describes as JSON (`emails`, `phones`, `linkedin_urls`, `name_hints`, `title`).
Use it to extract contacts from a URL directly instead of re-deriving the logic by hand.
