import os
from django.core.files import File
from delivery.models import ProductImage

image_folder = "/home/kali/Desktop/productImages"

image_list = sorted(os.listdir(image_folder))
product_image_list = ProductImage.objects.all()

for i in range(min(len(product_image_list), len(image_list))):
    filename = image_list[i]
    file_path = os.path.join(image_folder, filename)

    with open(file_path, 'rb') as f:
        django_file = File(f)
        product_image = product_image_list[i]
        product_image.image.save(filename, django_file, save=False)
        product_image.caption = os.path.splitext(filename)[0]
        product_image.alt = os.path.splitext(filename)[0]
        product_image.save()
