# node resource profile presets
resource_profiles = {
    "default": {
        "requests": {"cpu": "500m", "memory": "500Mi"},
        "limits": {"cpu": "1000m", "memory": "1500Mi"},
    },
    "raspberry_pi": {
        "requests": {"cpu": "100m", "memory": "128Mi"},
        "limits": {"cpu": "400m", "memory": "512Mi"},
    },
    "laptop": {
        "requests": {"cpu": "500m", "memory": "1Gi"},
        "limits": {"cpu": "2000m", "memory": "4Gi"},
    },
    "desktop": {
        "requests": {"cpu": "1000m", "memory": "2Gi"},
        "limits": {"cpu": "4000m", "memory": "8Gi"},
    },
    "server": {
        "requests": {"cpu": "2000m", "memory": "4Gi"},
        "limits": {"cpu": "8000m", "memory": "16Gi"},
    },
}
