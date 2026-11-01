"""Small search-engine discovery endpoints for the public landing page."""

from xml.sax.saxutils import escape

from django.http import HttpResponse
from django.urls import reverse


def robots_txt(request):
    """Allow crawling and point search engines to the public-page sitemap."""
    sitemap_url = request.build_absolute_uri(reverse("sitemap"))
    content = f"User-agent: *\nAllow: /\nSitemap: {sitemap_url}\n"
    return HttpResponse(content, content_type="text/plain")


def sitemap_xml(request):
    """List only the public landing page, never student-specific pages."""
    home_url = escape(request.build_absolute_uri(reverse("academics:home")))
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{home_url}</loc></url>\n"
        "</urlset>\n"
    )
    return HttpResponse(content, content_type="application/xml")

