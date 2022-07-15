import json
import requests
from tests.helpers import NetworkTest
import time

CONTROLLER = "127.0.0.1"
KYTOS_API = f"http://{CONTROLLER}:8181/api/kytos"


class TestE2EOfLLDPLinkLiveness:
    net = None

    @classmethod
    def setup_class(cls):
        cls.net = NetworkTest(CONTROLLER)
        cls.net.start()
        cls.net.wait_switches_connect()
        time.sleep(10)

    @classmethod
    def teardown_class(cls):
        cls.net.stop()

    def setup_method(self, method):
        """
        It is called at the beginning of every class method execution
        """
        self.net.start_controller(clean_config=True, enable_all=True)
        self.net.wait_switches_connect()
        time.sleep(10)

    def restart(self, clean_config=False, enable_all=True, wait_for=10):
        self.net.start_controller(clean_config=clean_config, enable_all=enable_all)
        self.net.wait_switches_connect()
        # Wait a few seconds to kytos execute LLDP
        time.sleep(wait_for)

    def enable_link_liveness(self, interface_ids):
        response = requests.post(
            KYTOS_API + "/of_lldp/v1/liveness/enable/",
            json={"interfaces": interface_ids},
        )
        assert response.status_code == 200, response.text
        return response

    def disable_link_liveness(self, interface_ids):
        response = requests.post(
            KYTOS_API + "/of_lldp/v1/liveness/disable/",
            json={"interfaces": interface_ids},
        )
        assert response.status_code == 200, response.text
        return response

    def set_polling_time(self, interval: int) -> None:
        """Set LLDP polling time"""
        response = requests.post(
            KYTOS_API + "/of_lldp/v1/polling_time/",
            json={"polling_time": interval},
        )
        assert response.status_code == 200, response.text
        return response

    def test_enable_link_liveness(self) -> None:
        """Test enable link liveness persistence."""
        polling_interval = 1
        self.set_polling_time(polling_interval)
        interface_ids = [
            "00:00:00:00:00:00:00:03:2",
            "00:00:00:00:00:00:00:02:3",
            "00:00:00:00:00:00:00:01:3",
            "00:00:00:00:00:00:00:02:2",
            "00:00:00:00:00:00:00:01:4",
            "00:00:00:00:00:00:00:03:3",
        ]
        intfs_grouped = []
        for i in range(0, len(interface_ids) - 1, 2):
            intfs_grouped.append((interface_ids[i], interface_ids[i + 1]))
            intfs_grouped.append((interface_ids[i + 1], interface_ids[i]))

        self.enable_link_liveness(interface_ids)

        # Wait a bit just so liveness can go up
        time.sleep(polling_interval * 5)

        # Assert GET liveness/ is all set
        api_url = f"{KYTOS_API}/of_lldp/v1/liveness/"
        response = requests.get(api_url)
        data = response.json()
        for entry in data["interfaces"]:
            assert entry["id"] in interface_ids, entry
            assert entry["status"] == "up", entry

        # Assert GET liveness/pair is all set
        api_url = f"{KYTOS_API}/of_lldp/v1/liveness/pair"
        response = requests.get(api_url)
        data = response.json()
        assert data["pairs"], data
        for entry in data["pairs"]:
            assert entry["status"] == "up", entry
            intfa_id = entry["interface_a"]["id"]
            intfb_id = entry["interface_b"]["id"]
            assert (intfa_id, intfb_id) in intfs_grouped

        # Assert link metadata has liveness_status "up"
        api_url = f"{KYTOS_API}/topology/v3/links"
        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["links"]
        for link in data["links"].values():
            if any(
                (
                    link["endpoint_a"]["id"] in interface_ids,
                    link["endpoint_b"]["id"] in interface_ids,
                )
            ):
                assert link["metadata"]["liveness_status"] == "up"

        # Restart the controller maintaining config
        self.restart(wait_for=15)

        # Assert GET liveness/ is still all set
        api_url = f"{KYTOS_API}/of_lldp/v1/liveness/"
        response = requests.get(api_url)
        data = response.json()
        for entry in data["interfaces"]:
            assert entry["id"] in interface_ids, entry
            assert entry["status"] == "up", entry

    def test_disable_link_liveness(self) -> None:
        """Test disable link liveness."""
        polling_interval = 1
        self.set_polling_time(polling_interval)
        interface_ids = [
            "00:00:00:00:00:00:00:03:2",
            "00:00:00:00:00:00:00:02:3",
            "00:00:00:00:00:00:00:01:3",
            "00:00:00:00:00:00:00:02:2",
            "00:00:00:00:00:00:00:01:4",
            "00:00:00:00:00:00:00:03:3",
        ]
        self.enable_link_liveness(interface_ids)

        # Wait a bit just so liveness can go up
        time.sleep(polling_interval * 5)

        # Assert GET liveness/ is enabled
        api_url = f"{KYTOS_API}/of_lldp/v1/liveness/"
        response = requests.get(api_url)
        data = response.json()
        for entry in data["interfaces"]:
            assert entry["id"] in interface_ids, entry
            assert entry["status"] == "up", entry

        self.disable_link_liveness(interface_ids)

        # Assert GET liveness/ is disabled
        api_url = f"{KYTOS_API}/of_lldp/v1/liveness/"
        response = requests.get(api_url)
        data = response.json()
        assert data["interfaces"] == []

        # Restart the controller maintaining config
        self.restart(wait_for=10)

        # Assert GET liveness/ is still disabled
        api_url = f"{KYTOS_API}/of_lldp/v1/liveness/"
        response = requests.get(api_url)
        data = response.json()
        assert data["interfaces"] == []

    def test_liveness_goes_down(self) -> None:
        """Test liveness goes down."""
        polling_interval = 1
        self.set_polling_time(polling_interval)
        interface_ids = [
            "00:00:00:00:00:00:00:01:3",
            "00:00:00:00:00:00:00:02:2",
        ]
        link_id = "78282c4d5b579265f04ebadc4405ca1b49628eb1d684bb45e5d0607fa8b713d0"
        self.enable_link_liveness(interface_ids)

        # Wait a bit just so liveness can go up
        time.sleep(polling_interval * 5)

        # Assert GET liveness/ is enabled
        api_url = f"{KYTOS_API}/of_lldp/v1/liveness/"
        response = requests.get(api_url)
        data = response.json()
        for entry in data["interfaces"]:
            assert entry["id"] in interface_ids, entry
            assert entry["status"] == "up", entry

        """
        Install a high prio LLDP flow to drop just so packet-ins
        are no longer sent. This will force hello to be missed.
        """
        payload = {
          "force": True,
          "flows": [
            {
              "cookie": int(0xdd00000000000000),
              "cookie_prefix": int(0xffffffffffffffff),
              "priority": 30000,
              "match": {
                "dl_type": int(0x88cc)
              }
            }
          ]
        }
        api_url = f"{KYTOS_API}/flow_manager/v2/flows/00:00:00:00:00:00:00:02"
        response = requests.post(api_url, data=json.dumps(payload),
                                 headers={'Content-type': 'application/json'})
        assert response.status_code == 202, response.text
        data = response.json()
        assert "FlowMod Messages Sent" in data["response"]

        # Wait a bit just so the flow is sent and hellos are missed
        time.sleep(10)

        # Assert GET liveness/ is enabled and down
        api_url = f"{KYTOS_API}/of_lldp/v1/liveness/?interface_id={interface_ids[1]}"
        response = requests.get(api_url)
        data = response.json()
        assert data["interfaces"], data["interfaces"]
        assert data["interfaces"][0]["id"] == interface_ids[1], data["interfaces"]
        assert data["interfaces"][0]["status"] == "down", data["interfaces"]

        # Assert link metadata has liveness_status "down"
        api_url = f"{KYTOS_API}/topology/v3/links"
        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["links"]
        metadata = data["links"][link_id]["metadata"]
        assert metadata["liveness_status"] == "down", metadata

        # Deletes the flow that was forcing hello misses
        api_url = f"{KYTOS_API}/flow_manager/v2/flows/00:00:00:00:00:00:00:02"
        response = requests.delete(api_url, data=json.dumps(payload),
                                   headers={'Content-type': 'application/json'})
        assert response.status_code == 202, response.text
        data = response.json()
        assert "FlowMod Messages Sent" in data["response"]

        # Wait a bit just so the flow is removed
        time.sleep(10)

        # Assert GET liveness/ is enabled and up
        api_url = f"{KYTOS_API}/of_lldp/v1/liveness/?interface_id={interface_ids[1]}"
        response = requests.get(api_url)
        data = response.json()
        assert data["interfaces"], data["interfaces"]
        assert data["interfaces"][0]["id"] == interface_ids[1], data["interfaces"]
        assert data["interfaces"][0]["status"] == "up", data["interfaces"]

        # Assert link metadata has liveness_status "up"
        api_url = f"{KYTOS_API}/topology/v3/links"
        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["links"]
        metadata = data["links"][link_id]["metadata"]
        assert metadata["liveness_status"] == "up", metadata
