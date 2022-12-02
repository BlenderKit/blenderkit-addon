import collections
import logging
import os


DAEMON_ACCESSIBLE = False
DAEMON_ONLINE = False
DATA = {
  'images available': {},
  'search history': collections.deque(maxlen=20),
  'bkit notifications': None,
  'asset comments': {},
}
LOGGING_LEVEL_BLENDERKIT = logging.INFO
LOGGING_LEVEL_IMPORTED = logging.WARN
PREFS = {}

SERVER = os.environ.get('BLENDERKIT_SERVER', 'https://www.blenderkit.com')

TIPS = [
  ('You can disable tips in the add-on preferences.', 'https://docs.blender.org/manual/en/3.1/addons/3d_view/blenderkit.html#preferences'),
  ('Ratings help us distribute funds to creators.', f'{SERVER}/docs/rating/'),
  ('Creators also gain credits for free assets from subscribers.', f'{SERVER}/docs/fair-share/'),
  ('Click or drag model or material in scene to link/append.', 'https://docs.blender.org/manual/en/3.1/addons/3d_view/blenderkit.html#basic-usage'),
  ('Right click in the asset bar for a detailed asset card.', 'https://docs.blender.org/manual/en/3.1/addons/3d_view/blenderkit.html#'),
  ('Use Append in import settings if you want to edit downloaded objects.', 'https://docs.blender.org/manual/en/3.1/addons/3d_view/blenderkit.html#import-method'),
  ('Go to import settings to set default texture resolution.', 'https://docs.blender.org/manual/en/3.1/addons/3d_view/blenderkit.html#import-method'),
  ('Please rate responsively and plentifully. This helps us distribute rewards to the authors.', f'{SERVER}/docs/rating/'),
  ('All materials are free.', f'{SERVER}/asset-gallery?query=category_subtree:material%20order:-created'),
  ('Storage for public assets is unlimited.', f'{SERVER}/become-creator/'),
  ('Locked models are available if you subscribe to Full plan.', f'{SERVER}/plans/pricing/'),
  ('Login to upload your own models, materials or brushes.', f'{SERVER}/'),
  ('Use \'A\' key over the asset bar to search assets by the same author.', 'https://docs.blender.org/manual/en/3.1/addons/3d_view/blenderkit.html#basic-usage'),
  ('Use semicolon - ; to hide or show the AssetBar.', 'https://docs.blender.org/manual/en/3.1/addons/3d_view/blenderkit.html#assetbar'),
  ('Support the authors by subscribing to Full plan.', f'{SERVER}/plans/pricing/'),
  ('Use the W key over the asset bar to open the Author\'s webpage.', 'https://docs.blender.org/manual/en/3.1/addons/3d_view/blenderkit.html#assetbar'),
  ('Use the R key over the asset bar for fast rating of assets.', 'https://docs.blender.org/manual/en/3.1/addons/3d_view/blenderkit.html#assetbar'),
  ('Use the X key over the asset bar to delete the asset from your hard drive.', 'https://docs.blender.org/manual/en/3.1/addons/3d_view/blenderkit.html#assetbar'),
  ('Get latest experimental versions of add-on by enabling prerelases in preferences.', ''),
]
VERSION = None  # filled in register()

daemon_process = None
