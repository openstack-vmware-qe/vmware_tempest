from tempest.api.compute import base as compute_base
from tempest.api.volume import base as volume_base
from tempest.common.utils import data_utils
from tempest import config

from vmware_tempest import test
from vmware_tempest import config as vmw_config

CONF = config.CONF
VCONF = vmw_config.CONF


class IsoScenarioTests(test.BaseVMwareTest):
    @classmethod
    def setUpClass(cls):
        super(IsoScenarioTests, cls).setUpClass()

        # Set helper functions from base api tests
        cls.compute = compute_base.BaseV2ComputeTest
        cls.compute.servers_client = cls.servers_client
        cls.compute.images_client = cls.images_client
        cls.compute.images = []
        cls.compute.servers = []
        cls.compute.flavor_ref = CONF.compute.flavor_ref
        cls.compute.image_ref = CONF.compute.image_ref

        cls.volume = volume_base.BaseVolumeV2Test
        cls.volume.volumes = []
        cls.volume.snapshots = []
        cls.volume.volumes_client = cls.volumes_client
        cls.volume.snapshots_client = cls.snapshots_client

        # Create a flavor with a root disk and one without
        cls.flavor = cls._create_flavor(1)
        cls.flavor_no_rd = cls._create_flavor(0)

    @classmethod
    def tearDownClass(cls):
        super(IsoScenarioTests, cls).tearDownClass()
        cls._clear_flavors()
        cls.compute.clear_images()
        cls.compute.clear_servers()
        cls.volume.clear_snapshots()
        cls.volume.clear_volumes()

    def test_boot(self):
        self._test_boot()

    def test_boot_no_root_disk(self):
        self._test_boot(root_disk=False)

    def test_snapshot_instance(self):
        self._test_snapshot_instance()

    def test_snapshot_instance_no_root_disk(self):
        self._test_snapshot_instance(root_disk=False)

    def test_boot_from_snapshot(self):
        self._test_boot_from_snapshot()

    def test_boot_from_volume(self):
        self._test_boot_from_volume()

    def test_boot_from_volume_snapshot(self):
        self._test_boot_from_volume_snapshot()

    def test_boot_from_image_copied_from_volume(self):
        self._test_boot_from_image_copied_from_volume()

    def test_attach_volume(self):
        # Boot the server
        server = self._test_boot()

        # Create volume
        volume_name = data_utils.rand_name(self.__class__.__name__ + "-vol")
        resp, volume = self.volumes_client.create_volume(
            1, display_name=volume_name)
        self.addCleanup(self._delete_volume, volume['id'])
        self.volumes_client.wait_for_volume_status(volume['id'], 'available')

        # Attach volume
        device = CONF.compute.volume_device_name
        self.servers_client.attach_volume(server['id'], volume['id'],
                                          device='/dev/%s' % device)
        self.volumes_client.wait_for_volume_status(volume['id'], 'in-use')
        self.addCleanup(self._detach_volume, server['id'], volume['id'])

    def _test_upload_iso_image(self, root_disk=True):
        # Upload the image
        iso_url = VCONF.get('DEFAULT', 'iso_image_url')
        if not iso_url:
            skip_msg = "Skipped as iso url was not set"
            raise self.__class__.skipException(skip_msg)

        # Create an image from specified url
        image_name = data_utils.rand_name(self.__class__.__name__ + "-image")
        resp, image = self.image_client.create_image(
            image_name, 'bare', 'iso', location=iso_url, is_public=True)
        self.compute.images.append(image['id'])
        return image

    def _test_boot(self, root_disk=True):
        # Upload an ISO image
        image = self._test_upload_iso_image(root_disk=root_disk)

        # Boot a server with created image
        flavor = self.flavor if root_disk else self.flavor_no_rd
        server_name = data_utils.rand_name(
            self.__class__.__name__ + "-instance")
        resp, body = self.compute.create_test_server(
            name=server_name, image_id=image['id'], wait_until='ACTIVE',
            flavor=flavor['id'])
        resp, server = self.servers_client.get_server(body['id'])
        self.addCleanup(self.servers_client.delete_server, server['id'])
        return server

    def _test_snapshot_instance(self, root_disk=True):
        # Boot the server
        server = self._test_boot(root_disk=root_disk)

        # Snapshot the instance (Note: if instance has no root disk, then
        # we expect the operation to fail. if so, the snapshot will have
        # DELETED state)
        wait_until = 'ACTIVE' if root_disk else 'DELETED'

        snapshot_name = data_utils.rand_name(
            self.__class__.__name__ + "-snapshot")
        resp, image = self.compute.create_image_from_server(
            server['id'], name=snapshot_name, wait_until=wait_until)
        return image

    def _test_boot_from_snapshot(self):
        # Boot the server and snapshot it
        image = self._test_snapshot_instance()

        # Boot from the snapshot
        server_name = data_utils.rand_name(
            self.__class__.__name__ + "-instance")
        resp, body = self.compute.create_test_server(
            name=server_name, image_id=image['id'], wait_until='ACTIVE')
        resp, server = self.servers_client.get_server(body['id'])
        self.assertEqual(server['status'], 'ACTIVE')

    def _test_create_volume(self):
        # Boot the server and snapshot it
        image = self._test_snapshot_instance()

        # Copy snapshot to volume
        volume_name = data_utils.rand_name(self.__class__.__name__ + "-volume")
        resp, volume = self.volumes_client.create_volume(
            1, display_name=volume_name, imageRef=image['id'])
        self.volume.volumes.append(volume)
        self.volumes_client.wait_for_volume_status(volume['id'], 'available')
        return volume

    def _test_boot_from_volume(self):
        # Boot server, snapshot and copy to volume
        volume = self._test_create_volume()

        # Boot from volume
        self._boot_from_block_device_mapping(volume['id'])

    def _test_boot_from_volume_snapshot(self):
        # Boot server, snapshot and copy to volume
        volume = self._test_create_volume()

        # Snapshot volume
        snapshot = self.volume.create_snapshot(volume['id'])

        # Boot from volume snapshot
        self._boot_from_block_device_mapping(snapshot['id'], is_snap=True)

    def _test_boot_from_image_copied_from_volume(self):
        # Boot server, snapshot and copy to volume
        volume = self._test_create_volume()

        # Copy volume to image
        image_name = data_utils.rand_name(self.__class__.__name__ + "-image")
        resp, body = self.volumes_client.upload_volume(
            volume['id'], image_name, CONF.volume.disk_format)
        image_id = body["image_id"]
        self.compute.images.append({'id': image_id})
        self.image_client.wait_for_image_status(image_id, 'active')
        self.volumes_client.wait_for_volume_status(self.volume['id'],
                                                   'available')

        # Boot from image
        server_name = data_utils.rand_name(
            self.__class__.__name__ + "-instance")
        resp, body = self.compute.create_test_server(
            name=server_name, image_id=image_id, wait_until='ACTIVE')
        resp, server = self.servers_client.get_server(body['id'])

    def _boot_from_block_device_mapping(self, resource_id, is_snap=False):
        voltype = 'snap' if is_snap else ''
        bd_map = {'vda': '%s:%s::0' % (resource_id, voltype)}

        server_name = data_utils.rand_name(self.__class__.__name__ + "-volume")
        server = self.nova_client.servers.create(
            server_name, None, '1', block_device_mapping=bd_map)
        self.compute.servers.append({'id': server.id})
        self.servers_client.wait_for_server_status(server.id, 'ACTIVE')
        return server

    @classmethod
    def _create_flavor(cls, disk_size):
        flavor_name = data_utils.rand_name(cls.__name__ + '-flavor')
        resp, flavor = cls.flavors_client.create_flavor(
            flavor_name, 512, 1, disk_size, None)
        return flavor

    @classmethod
    def _clear_flavors(cls):
        try:
            cls.flavors_client.delete_flavor(cls.flavor)
            cls.flavors_client.delete_flavor(cls.flavor_no_rd)
        except:
            # We might come here due to side effects of failed tests
            pass

    def _detach_volume(self, server_id, volume_id):
        self.servers_client.detach_volume(server_id, volume_id)
        self.volumes_client.wait_for_volume_status(volume_id, 'available')

    def _delete_volume(self, volume_id):
        self.volumes_client.delete_volume(volume_id)
        self.volumes_client.wait_for_resource_deletion(volume_id)
