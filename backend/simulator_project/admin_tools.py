"""
Helpers shared by the admin pages of the apps.

RunButtonMixin adds a "Save and calculate" button to the change form of the
objects that can be calculated (cost simulations, optimisations, cold-room
simulations) and a matching list action, so users never have to go back to
the list and pick an action to run what they just entered.
"""

from django.conf import settings
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html


def frontend_url(path):
    """URL of a page of the results website (served on the same address in Docker)."""
    return f"{settings.FRONTEND_URL.rstrip('/')}/{path.lstrip('/')}"


def frontend_link(path, label):
    return format_html('<a href="{}" target="_blank" rel="noopener">{} ↗</a>', frontend_url(path), label)


def euros(value):
    return '–' if value is None else f'€{value:,.2f}'


class RunButtonMixin:
    """
    Subclasses set `run_button_label` and implement run_object(obj), which
    performs the calculation and returns a success message (or raises).
    """
    change_form_template = 'admin/sparc/change_form_with_run.html'
    run_button_label = 'Save and calculate'
    actions = ['run_selected']
    result_fields = ()  # Fields that do not change the result (everything else does)

    def run_object(self, obj):
        raise NotImplementedError

    def clear_results(self, obj):
        """Forget the result of `obj`, which no longer matches its settings. Returns True if there was one."""
        raise NotImplementedError

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change and set(form.changed_data) - {'name', 'notes', *self.result_fields}:
            if self.clear_results(obj) and '_run' not in request.POST:
                self.message_user(request, 'The settings changed, so the previous result was removed: '
                                           f'press "{self.run_button_label}" to get the new one.', messages.WARNING)

    def _run_and_report(self, request, obj):
        try:
            message = self.run_object(obj)
        except Exception as e:  # The message is shown to the user in the page
            self.message_user(request, f'"{obj}" could not be calculated: {e}', level=messages.ERROR)
            return False
        self.message_user(request, message, level=messages.SUCCESS)
        return True

    def render_change_form(self, request, context, *args, **kwargs):
        context['run_button_label'] = self.run_button_label
        return super().render_change_form(request, context, *args, **kwargs)

    def _response_after_save(self, request, obj, default_response):
        if '_run' not in request.POST:
            return default_response
        self._run_and_report(request, obj)
        opts = obj._meta
        return HttpResponseRedirect(reverse(f'admin:{opts.app_label}_{opts.model_name}_change', args=[obj.pk]))

    def response_add(self, request, obj, post_url_continue=None):
        return self._response_after_save(request, obj, super().response_add(request, obj, post_url_continue))

    def response_change(self, request, obj):
        return self._response_after_save(request, obj, super().response_change(request, obj))

    @admin.action(description='Calculate the selected items')
    def run_selected(self, request, queryset):
        for obj in queryset:
            self._run_and_report(request, obj)
