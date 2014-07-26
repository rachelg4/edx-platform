"""
Module for code that should run during LMS startup
"""

from django.conf import settings

# Force settings to run so that the python path is modified
settings.INSTALLED_APPS  # pylint: disable=W0104

from django_startup import autostartup
import edxmako
import logging

# Imports required for Monkeypatching keyword substitution module
from util import keyword_substitution
from django.contrib.auth.models import User
from util.date_utils import get_default_time_display

log = logging.getLogger(__name__)
kf_map = {}

def run():
    """
    Executed during django startup
    """
    autostartup()

    add_mimetypes()

    if settings.FEATURES.get('USE_CUSTOM_THEME', False):
        enable_theme()

    if settings.FEATURES.get('USE_MICROSITES', False):
        enable_microsites()

    if settings.FEATURES.get('ENABLE_THIRD_PARTY_AUTH', False):
        enable_third_party_auth()

    # Monkey patch the keyword function map
    keyword_substitution.add_keyword_function_map(get_keyword_function_map())

def add_mimetypes():
    """
    Add extra mimetypes. Used in xblock_resource.

    If you add a mimetype here, be sure to also add it in cms/startup.py.
    """
    import mimetypes

    mimetypes.add_type('application/vnd.ms-fontobject', '.eot')
    mimetypes.add_type('application/x-font-opentype', '.otf')
    mimetypes.add_type('application/x-font-ttf', '.ttf')
    mimetypes.add_type('application/font-woff', '.woff')


def enable_theme():
    """
    Enable the settings for a custom theme, whose files should be stored
    in ENV_ROOT/themes/THEME_NAME (e.g., edx_all/themes/stanford).
    """
    # Workaround for setting THEME_NAME to an empty
    # string which is the default due to this ansible
    # bug: https://github.com/ansible/ansible/issues/4812
    if settings.THEME_NAME == "":
        settings.THEME_NAME = None
        return

    assert settings.FEATURES['USE_CUSTOM_THEME']
    settings.FAVICON_PATH = 'themes/{name}/images/favicon.ico'.format(
        name=settings.THEME_NAME
    )

    # Calculate the location of the theme's files
    theme_root = settings.ENV_ROOT / "themes" / settings.THEME_NAME

    # Include the theme's templates in the template search paths
    settings.TEMPLATE_DIRS.insert(0, theme_root / 'templates')
    edxmako.paths.add_lookup('main', theme_root / 'templates', prepend=True)

    # Namespace the theme's static files to 'themes/<theme_name>' to
    # avoid collisions with default edX static files
    settings.STATICFILES_DIRS.append(
        (u'themes/{}'.format(settings.THEME_NAME), theme_root / 'static')
    )


def enable_microsites():
    """
    Enable the use of microsites, which are websites that allow
    for subdomains for the edX platform, e.g. foo.edx.org
    """

    microsites_root = settings.MICROSITE_ROOT_DIR
    microsite_config_dict = settings.MICROSITE_CONFIGURATION

    for ms_name, ms_config in microsite_config_dict.items():
        # Calculate the location of the microsite's files
        ms_root = microsites_root / ms_name
        ms_config = microsite_config_dict[ms_name]

        # pull in configuration information from each
        # microsite root

        if ms_root.isdir():
            # store the path on disk for later use
            ms_config['microsite_root'] = ms_root

            template_dir = ms_root / 'templates'
            ms_config['template_dir'] = template_dir

            ms_config['microsite_name'] = ms_name
            log.info('Loading microsite {0}'.format(ms_root))
        else:
            # not sure if we have application logging at this stage of
            # startup
            log.error('Error loading microsite {0}. Directory does not exist'.format(ms_root))
            # remove from our configuration as it is not valid
            del microsite_config_dict[ms_name]

    # if we have any valid microsites defined, let's wire in the Mako and STATIC_FILES search paths
    if microsite_config_dict:
        settings.TEMPLATE_DIRS.append(microsites_root)
        edxmako.paths.add_lookup('main', microsites_root)

        settings.STATICFILES_DIRS.insert(0, microsites_root)


def enable_third_party_auth():
    """
    Enable the use of third_party_auth, which allows users to sign in to edX
    using other identity providers. For configuration details, see
    common/djangoapps/third_party_auth/settings.py.
    """

    from third_party_auth import settings as auth_settings
    auth_settings.apply_settings(settings.THIRD_PARTY_AUTH, settings)


def get_keyword_function_map():
    """
    Define the mapping of keywords and functions that will be used to filter
    html, text and email strings before rendering them.

    The generated map will be monkey-patched onto the keyword_substitution
    module so that it persists along with the running server.

    Each function must take: user & course as parameters
    """

    from student.models import anonymous_id_for_user
    def user_id_sub(user, course):
        # For compatibility with the existing anon_ids, return anon_id without course_id
        return anonymous_id_for_user(user, course.id)

    def user_fullname_sub(user, course=None):
        return user.profile.name

    def course_display_name_sub(user, course):
        return course.display_name

    def course_end_date_sub(user, course):
        return get_default_time_display(course.end)

    # Define keyword - function map
    kf_map = {
        '%%USER_ID%%': user_id_sub,
        '%%USER_FULLNAME%%': user_fullname_sub,
        '%%COURSE_DISPLAY_NAME%%': course_display_name_sub,
        '%%COURSE_END_DATE%%': course_end_date_sub
    }

    return kf_map
