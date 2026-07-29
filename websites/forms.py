from urllib.parse import urlparse, urlunparse

from django import forms


class AddWebsiteForm(forms.Form):
    url = forms.CharField(max_length=500)

    def clean_url(self):
        raw = self.cleaned_data["url"].strip()
        if "://" not in raw:
            raw = f"https://{raw}"
        parsed = urlparse(raw)
        if parsed.scheme not in ("http", "https"):
            raise forms.ValidationError("Only http and https URLs are supported.")
        if not parsed.netloc or "." not in parsed.netloc:
            raise forms.ValidationError("Enter a valid website URL.")
        # Keep only the site origin
        return urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))


class ContentAPIKeyForm(forms.Form):
    api_key = forms.CharField(max_length=200)
