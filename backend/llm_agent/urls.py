from django.urls import path
from . import views

urlpatterns = [
    path('generate-sql/', views.generate_sql_from_nl, name='generate-sql'),
    # Removed redundant generate-description endpoint
]