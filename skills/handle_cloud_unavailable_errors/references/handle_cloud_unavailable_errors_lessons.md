def handle_cloud_unavailable_error(response):
    if 'Cloud unavailable' in response:
        return "Please try again or disable complex reasoning."
    return response