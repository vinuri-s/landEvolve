from app.services.vegetation_service import VegetationService


class VegetationController:
    """
    Links the vegetation configuration UI to VegetationService so the UI never
    accesses the database directly.
    """

    def __init__(self):
        self.service = VegetationService()

    def get_classes(self):
        return self.service.get_all_classes()

    def get_class(self, class_id):
        return self.service.get_class(class_id)

    def create_class(self, **kwargs):
        return self.service.create_class(**kwargs)

    def update_class(self, class_id, **kwargs):
        return self.service.update_class(class_id, **kwargs)

    def delete_class(self, class_id):
        self.service.delete_class(class_id)
