from tempest import clients
from tempest.common import isolated_creds
from tempest import config
from tempest.openstack.common import log as logging
import tempest.test

CONF = config.CONF

LOG = logging.getLogger(__name__)


class BaseVMwareTest(tempest.test.BaseTestCase):
    def __init__(self, *args, **kwargs):
        super(BaseVMwareTest, self).__init__(*args, **kwargs)

    @classmethod
    def setUpClass(cls):
        super(BaseVMwareTest, cls).setUpClass()

        # Create isolated login with admin access
        cls.isolated_creds = isolated_creds.IsolatedCreds(
            cls.__name__, network_resources=cls.network_resources)
        creds = cls.isolated_creds.get_admin_creds()
        admin_username, admin_tenant_name, admin_password = creds
        cls.os = clients.Manager(username=admin_username,
                                 password=admin_password,
                                 tenant_name=admin_tenant_name)
        cls.os_ofc = clients.OfficialClientManager(
            admin_username, admin_password, admin_tenant_name)

        # Set references to service clients
        cls.servers_client = cls.os.servers_client
        cls.image_client = cls.os.image_client
        cls.images_client = cls.os.images_client
        cls.flavors_client = cls.os.flavors_client
        cls.volumes_client = cls.os.volumes_client
        cls.snapshots_client = cls.os.snapshots_client

        # Set official clients
        cls.nova_client = cls.os_ofc.compute_client

    @classmethod
    def tearDownClass(cls):
        super(BaseVMwareTest, cls).tearDownClass()
        cls.clear_isolated_creds()
