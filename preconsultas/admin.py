from django.contrib import admin

from .models import Clinic, Doctor, ReceptionProfile


@admin.register(Clinic)
class ClinicAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ["name", "display_registration", "user"]
    search_fields = ["name", "display_registration"]
    filter_horizontal = ["clinics"]


@admin.register(ReceptionProfile)
class ReceptionProfileAdmin(admin.ModelAdmin):
    list_display = ["user"]
    filter_horizontal = ["clinics"]

# Clinical models deliberately remain unregistered, even for superusers.
