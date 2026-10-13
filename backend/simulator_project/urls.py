"""
URL configuration for simulator_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.contrib.auth.models import Group
from django.urls import path, include

admin.site.site_header = 'SPARC · energy planning for CONCAST'
admin.site.site_title = 'SPARC'
admin.site.index_title = 'Data and calculations'
admin.site.site_url = (settings.FRONTEND_URL or '') + '/'
# Permissions are managed per user; groups are not needed for a single plant
admin.site.unregister(Group)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/datasets/', include('DatasetApp.urls')),
    path('api/planning/', include('PlanningApp.urls')),
    path('api/chillers/', include('ChillersApp.urls')),
    path('api/simulation/', include('SimulationApp.urls')),
    path('api/optimizer/', include('OptimizerApp.urls')),
]
