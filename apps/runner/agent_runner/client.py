import httpx
from .config import config
class Client:
    def __init__(self): self.base=config.control_plane_url.rstrip("/")
    @property
    def headers(self): return {"X-Runner-Token":config.runner_token}
    def register(self,hostname):
        response=httpx.post(self.base+"/v1/runners/register",json={"id":config.runner_id,"token":config.runner_token,"os_name":config.runner_os,"hostname":hostname},timeout=20); response.raise_for_status()
    def heartbeat(self):
        response=httpx.post(self.base+f"/v1/runners/{config.runner_id}/heartbeat",json={"token":config.runner_token,"status":"online"},timeout=20); response.raise_for_status()
    def next_task(self):
        response=httpx.get(self.base+f"/v1/runners/{config.runner_id}/next",headers=self.headers,timeout=30); response.raise_for_status(); return response.json()["task"]
    def update(self,task_id,status,plan=None,result=None,error=None):
        response=httpx.post(self.base+f"/v1/runners/{config.runner_id}/tasks/{task_id}",headers=self.headers,json={"status":status,"plan":plan,"result":result,"error":error},timeout=30); response.raise_for_status(); return response.json()
