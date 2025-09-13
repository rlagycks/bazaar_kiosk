from __future__ import annotations
from django import forms

class CSVUploadForm(forms.Form):
    file = forms.FileField(label="CSV 파일 (.csv)")
    MODE_CHOICES = [("upsert", "업서트(있으면 수정, 없으면 생성)"),
                    ("insert", "삽입만(기존 있으면 건너뜀)")]
    mode = forms.ChoiceField(choices=MODE_CHOICES, initial="upsert", label="처리 모드")
    # MenuItem 전용 옵션
    create_missing_category = forms.BooleanField(
        required=False, initial=True, label="없는 카테고리는 자동 생성"
    )