from django.contrib import admin

from .models import (
    Consultation,
    Correction,
    DoctorNote,
    Feedback,
    OperationalEvent,
    SourceItem,
    SummaryItem,
)


admin.site.register(
    [
        Consultation,
        Correction,
        DoctorNote,
        Feedback,
        OperationalEvent,
        SourceItem,
        SummaryItem,
    ]
)
