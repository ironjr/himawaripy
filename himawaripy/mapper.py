import math

from PIL import Image
import cv2
import numpy as np


class Mapper(object):
    def __init__(self, level=20, offset=(5, 2), scale=1.0, center=""):
        self.level = level
        self.offset = offset

        ##
        # Some magic numbers
        ##

        # Map constant
        self.km_per_pixel = scale

        # Satellite coordinate in radian
        # Assume satellite is infinitely far away
        self.sat_lat = math.radians(0.03) # 0.03 degree
        self.sat_long = math.radians(143.5) # 140.7 degree East

        # Korean peninsula coordinate
        self.kor_lat = math.radians(37.5665)
        self.kor_long = math.radians(126.9780)

        # Parse the map center coordinate
        if center is None or center == "":
            self.ctr_lat = self.kor_lat - math.radians(3.0)
            self.ctr_long = self.kor_long
        else:
            center = [float(c.strip()) for c in center.split(",")]
            self.ctr_lat = math.radians(center[0])
            self.ctr_long = math.radians(center[1])

        # Radius of the Earth
        self.earth_rad_im = 1 - 40.0 / 4400 # relative to the image width
        self.earth_rad_km = 6371.0 # km

        # Width of himawari satellite patches
        self.him_width = 550
        self.him_height = 550

    def earth_to_cartesian(self, earth_coord, longitude=0.0):
        # self.him_width == self.him_height
        imsize = self.him_width * self.level
        xoff, yoff = self.offset

        x_earth = earth_coord[0, :]
        y_earth = earth_coord[1, :]
        x_earth += xoff * self.him_width
        y_earth += yoff * self.him_height

        # Prime coordinate is the Cartesian coordinate with the satellite on the x-axis
        # Coordinates are normalized by the Earth radius
        y_prime = ( 2.0 * x_earth / float(imsize) - 1.0) / self.earth_rad_im
        z_prime = (-2.0 * y_earth / float(imsize) + 1.0) / self.earth_rad_im
        x_prime = math.sqrt(1.0 - y_prime * y_prime - z_prime * z_prime)

        # Convert to the standard Cartesian coordinate
        prime_coord = np.array([x_prime, y_prime, z_prime])

        theta_prime = math.pi * 0.5 - self.sat_lat
        phi_prime = self.sat_long - longitude

        sin_th_p = math.sin(theta_prime)
        cos_th_p = math.cos(theta_prime)
        sin_ph_p = math.sin(phi_prime)
        cos_ph_p = math.cos(phi_prime)

        prime_to_std = np.array([
            [sin_th_p * cos_ph_p, -sin_ph_p, -cos_th_p * cos_ph_p],
            [sin_th_p * sin_ph_p,  cos_ph_p, -cos_th_p * sin_ph_p],
            [           cos_th_p,         0,             sin_th_p]
        ])

        return prime_to_std.dot(prime_coord.reshape(3, -1)) \
                .reshape(prime_coord.shape)

    def cartesian_to_earth(self, std_coord, longitude=0.0):
        theta_prime = math.pi * 0.5 - self.sat_lat
        phi_prime = self.sat_long - longitude

        sin_th_p = math.sin(theta_prime)
        cos_th_p = math.cos(theta_prime)
        sin_ph_p = math.sin(phi_prime)
        cos_ph_p = math.cos(phi_prime)

        std_to_prime = np.array([
            [ sin_th_p * cos_ph_p,  sin_th_p * sin_ph_p, cos_th_p],
            [           -sin_ph_p,             cos_ph_p,        0],
            [-cos_th_p * cos_ph_p, -cos_th_p * sin_ph_p, sin_th_p]
        ])
        prime_coord = std_to_prime.dot(std_coord.reshape(3, -1)) \
                .reshape(std_coord.shape)

        x_prime = prime_coord[0, :]
        y_prime = prime_coord[1, :]
        z_prime = prime_coord[2, :]

        # self.him_width == self.him_height
        imsize = self.him_width * self.level

        x_earth = ( y_prime * self.earth_rad_im + 1.0) * float(imsize) * 0.5
        y_earth = (-z_prime * self.earth_rad_im + 1.0) * float(imsize) * 0.5

        xoff, yoff = self.offset
        x_earth -= xoff * self.him_width
        y_earth -= yoff * self.him_height

        return np.stack([x_earth, y_earth], axis=0)

    def cartesian_to_map(self, std_coord):
        x_std = std_coord[0, :]
        y_std = std_coord[1, :]
        z_std = std_coord[2, :]

        # Lambert azimuthal equal-area projection
        temp = np.sqrt(2.0 / (1.0 + z_std))
        x_map = temp.multiply(x_std)
        y_map = temp.multiply(y_std)
        
        # Correct the map coordinate with the map center
        # TODO

        return (x_map, y_map)

    def map_to_cartesian(self, width, height):
        # Make the map coordinate with respect to the map center and scale.
        # The map rectangle is on the x-axis of the projection plane,
        # rotated 90 degrees.
        #  earth_rad_px = 0.5 * self.level * self.him_width * self.earth_rad_im # pixels
        scale = self.km_per_pixel / self.earth_rad_km
        scale /= (2.0 * math.cos(self.ctr_lat))
        y_lin = (np.arange(width) - width * 0.5) * scale
        x_lin = (np.arange(height) - height * 0.5) * scale

        # The map ractangle is placed with x-offset.
        ctr_offset = 2.0 * (1.0 - math.sin(self.ctr_lat))
        x_lin += ctr_offset
        y_map, x_map = np.meshgrid(y_lin, x_lin)

        sum_of_sq = np.multiply(x_map, x_map) + np.multiply(y_map, y_map)
        factor = np.sqrt(1.0 - sum_of_sq * 0.25)

        # Inverse Lambert azimuthal equal-area projection
        x_std = np.multiply(x_map, factor)
        y_std = np.multiply(y_map, factor)
        z_std = 1.0 - sum_of_sq * 0.5

        return np.stack([x_std, y_std, z_std], axis=0)

    def get_map_transforms(self, width, height):
        std_coord = self.map_to_cartesian(width, height)
        earth_coord = self.cartesian_to_earth(std_coord, longitude=self.ctr_long)

        x_earth = earth_coord[0, :].astype(np.float32)
        y_earth = earth_coord[1, :].astype(np.float32)

        return x_earth, y_earth
    
    def transform(self, src, width, height):
        src = np.array(src)
        map_to_x, map_to_y = self.get_map_transforms(
            width=int(width),
            height=int(height)
        )
        res = cv2.remap(src, map_to_x, map_to_y, cv2.INTER_CUBIC)

        return Image.fromarray(res)
    
    def print_coordinates(self, coord):
        _, h, w = coord.shape
        print(
            'lt',   coord[:,      0,      0],
            '\tmt', coord[:,      0, w // 2],
            '\trt', coord[:,      0,     -1]
        )
        print(
            'lm',   coord[:, h // 2,      0],
            '\tmm', coord[:, h // 2, w // 2],
            '\trm', coord[:, h // 2,     -1]
        )
        print(
            'lb',   coord[:,     -1,      0],
            '\tmb', coord[:,     -1, w // 2],
            '\trb', coord[:,     -1,     -1]
        )


#  if __name__ == "__main__":
#      level = 20
#      offset = (5, 2)
#
#      mapper = Mapper(level=level, offset=offset, scale=4.0)
#
#      im = Image.open("original.png")
#      np_im = np.array(im)
#      print(np_im.shape)
#
#      map_to_x, map_to_y = mapper.get_map_transforms(width=1920, height=1080)
#      print(map_to_x.max(), map_to_x.min(), map_to_x.shape)
#      print(map_to_y.max(), map_to_y.min(), map_to_y.shape)
#
#      res = cv2.remap(np_im, map_to_x, map_to_y, cv2.INTER_CUBIC)
#      print(res.shape)
#      Image.fromarray(res).save("result.png", "PNG")
    

