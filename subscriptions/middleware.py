from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages


class SubscriptionRequiredMiddleware:
    """Middleware to enforce subscription requirements across the app"""

    def __init__(self, get_response):
        self.get_response = get_response

        # URLs that don't require subscription
        self.exempt_urls = [
            '/admin/',
            '/login/',
            '/logout/',
            '/signup/',
            '/register/',
            '/subscriptions/',
            '/subscriptions/pricing/',
            '/subscriptions/checkout/',
            '/subscriptions/success/',
            '/subscriptions/webhook/',
            '/__reload__/',
        ]

    def __call__(self, request):
        # Check if user needs subscription for this URL
        if self.requires_subscription(request):
            if not request.user.is_authenticated:
                # Redirect to login
                messages.info(request, "Please sign in to access PostFlow.")
                return redirect('login')
            elif not request.user.is_subscribed:
                # Redirect to pricing
                messages.info(request, "Subscribe to PostFlow Premium to access all features.")
                return redirect('subscriptions:pricing')

        response = self.get_response(request)
        return response

    def requires_subscription(self, request):
        """Check if the current URL requires a subscription"""
        path = request.path

        # Check if URL is exempt
        for exempt_url in self.exempt_urls:
            if path.startswith(exempt_url):
                return False

        # All other URLs require subscription
        return True