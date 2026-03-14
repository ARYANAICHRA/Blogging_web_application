#!/usr/bin/env python3
"""Generate a default avatar SVG as PNG for users with no avatar."""
import os

SVG = '''<svg width="200" height="200" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
  <rect width="200" height="200" fill="#e8e6e0"/>
  <circle cx="100" cy="80" r="40" fill="#c8b8a8"/>
  <ellipse cx="100" cy="175" rx="60" ry="40" fill="#c8b8a8"/>
</svg>'''

os.makedirs('app/static/img', exist_ok=True)
os.makedirs('app/static/uploads/avatars', exist_ok=True)
os.makedirs('app/static/uploads/posts', exist_ok=True)

# Write SVG as default avatar (browsers render SVG inline fine)
with open('app/static/img/default.png', 'wb') as f:
    # Write a minimal 1x1 transparent PNG as true fallback
    import base64
    PNG_1x1 = base64.b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
    )
    f.write(PNG_1x1)

with open('app/static/img/default_avatar.svg', 'w') as f:
    f.write(SVG)

print("Static assets initialized.")
