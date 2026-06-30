from django import forms
from goodies.forms import CrispyBaseModelForm
from goodies.widgets import BootstrapDateTimeInput

from tasks.models import TaskItem

__author__ = 'andrei'


class TaskItemForm(CrispyBaseModelForm):
    class Meta:
        model = TaskItem
        exclude = ("owner", "parent_task", "status")


    start_date = forms.DateTimeField(widget=BootstrapDateTimeInput, required=True)
    end_date = forms.DateTimeField(widget=BootstrapDateTimeInput, required=False)
