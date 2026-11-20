from django.contrib.contenttypes.apps import ContentTypesConfig

class MongoContentTypesConfig(ContentTypesConfig):
    """contenttypes de Django usando ObjectId como clave primaria."""
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"