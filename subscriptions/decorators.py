from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from functools import wraps


def subscription_required(view_func):
    """Decorator to require active subscription"""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_subscribed:
            messages.info(request, "Subscribe to PostFlow Premium to access this feature.")
            return redirect('subscriptions:pricing')
        return view_func(request, *args, **kwargs)
    return wrapper