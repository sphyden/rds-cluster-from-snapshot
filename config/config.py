import yaml

class Config(object):
    def __init__(self):
        self.config_path = "config/config.yml"
        self.config_file = None

    def get_config_file(self):
        with open(self.config_path, 'r') as f:
            self.config_file = yaml.load(f, Loader=yaml.FullLoader)
        return self.config_file
