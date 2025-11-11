import argparse
import json
import os
import shutil
import time
import hashlib

from PIL import Image
import requests
import yaml
import pillow_heif

# Register HEIC decoder
pillow_heif.register_heif_opener()

def compress_image(input_path: str, output_dir: str, lossy_quality=80) -> str:
    """
    Compress the image and save it to the output_dir
    :param input_path: the path of the image to compress
    :param output_dir: the directory to save the compressed image
    :param lossy_quality: the quality of the lossy compression
    :return: the path of the compressed image
    """
    # Get the filename from the input_path
    filename = os.path.basename(input_path)

    # Open the image
    image = Image.open(input_path)

    if image.format == 'GIF':  # for GIF images
        output_path = os.path.join(output_dir, filename)  # Keep the original extension for GIF
        shutil.copy(input_path, output_path)  # Copy the GIF image to the output_dir
        return output_path

    # For non-GIF images, change the extension to .webp
    filename = os.path.splitext(filename)[0] + '.webp'
    output_path = os.path.join(output_dir, filename)

    # Save as lossless WebP
    lossless_output_path = output_path.replace('.webp', '_lossless.webp')
    image.save(lossless_output_path, 'webp', lossless=True, save_all=True)
    lossless_size = os.path.getsize(lossless_output_path)

    # Calculate file size before lossy compression
    image.save(output_path, 'webp', quality=lossy_quality, save_all=True)
    lossy_size = os.path.getsize(output_path)

    # Choose the smallest file size and delete the other
    if lossless_size < lossy_size:
        os.remove(output_path)
        os.rename(lossless_output_path, output_path)
    else:
        os.remove(lossless_output_path)

    # Return the actual output_path
    return output_path


class Drive:
    """
    OneDrive API
    """

    def __init__(self):
        self.GRAPH_URL = 'https://graph.microsoft.com/v1.0'
        self.s = requests.Session()
        with open('config.yaml', 'r') as f:
            self.config = yaml.safe_load(f)

    def refresh_access_token(self):
        """
        Refresh the access token
        """
        data = {
            'client_id': self.config['client_id'],
            'redirect_uri': 'http://localhost:5000/callback',
            'client_secret': self.config['client_secret'],
            'refresh_token': self.config['refresh_token'],
            'grant_type': 'refresh_token'
        }
        r = self.s.post('https://login.microsoftonline.com/common/oauth2/v2.0/token', data=data)
        # print(json.dumps(r.json()))
        self.config['access_token'] = r.json()['access_token']
        self.config['refresh_token'] = r.json()['refresh_token']
        self.config['expires_at'] = int(time.time()) + r.json()['expires_in']
        with open('config.yaml', 'w') as f:
            yaml.safe_dump(self.config, f)

    def get_access_token(self) -> str:
        """
        Get the access token
        :return: Graph API access token
        """
        if self.config['expires_at'] < int(time.time()) - 60:
            self.refresh_access_token()
        return self.config['access_token']

    def generate_header(self) -> dict:
        """
        Generate the header for the request
        :return: the header
        """
        return {'Authorization': f'Bearer {self.get_access_token()}',
                'User-Agent': 'Typora Image Uploader(lrhtony0@gmail.com)'}

    def upload_by_path(self, drive_file_path: str, file_path: str) -> dict:
        """
        Upload a file to the drive by path
        :param drive_file_path: the path of the file in OneDrive
        :param file_path: the path of the file to upload
        :return: the response of the request
        """
        r = self.s.put(f'{self.GRAPH_URL}/me/drive/items/root:/{drive_file_path}:/content',
                       headers=self.generate_header(),
                       data=open(file_path, 'rb'))
        return r.json()


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))  # Change the working directory to the script's directory
    parser = argparse.ArgumentParser(description='Typora Image Uploader')
    parser.add_argument('--file', '-f', help='the path of the markdown file')
    parser.add_argument('args', nargs='*', help='upload images path')
    
    args = parser.parse_args()

    host_img_base_dir = 'host/blog/post/'
    if args.file is not None and args.file != "":
        article_time = os.path.getctime(args.file)
        article_title = os.path.basename(args.file).replace('.md', '')
        host_img_base_dir += f'{time.strftime("%Y%m%d", time.localtime(article_time))}-{article_title}/'
    else:
        host_img_base_dir += 'temp/'

    drive = Drive()
    img_url_base = 'https://img.0a0.moe/od/'
    for img_path in args.args:
        # 判断是本地图片还是网络图片，如果是网络图片则先下载
        if img_path.startswith('http'):
            # 如果host为img.jks.moe，则直接使用原图
            if 'img.jks.moe' in img_path or 'img.0a0.moe' in img_path:
                print(img_path)
                break
            img_url = img_path
            img_name = os.path.basename(hashlib.md5(img_url.encode()).hexdigest())
            img_path = f'temp/{img_name}'
            with open(img_path, 'wb') as f:
                f.write(requests.get(img_url).content)
        compressed_img_path = compress_image(img_path, 'temp')
        img_name = os.path.basename(compressed_img_path)
        upload_info = drive.upload_by_path(f'{host_img_base_dir}{img_name}', compressed_img_path)
        file_id = upload_info['id']
        img_url = f'{img_url_base}{file_id.lower()}'
        print(img_url)
        os.remove(compressed_img_path)
