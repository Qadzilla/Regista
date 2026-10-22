"""The Player view: a (synthetic) player uploads their match footage, Regista's vision workflow runs on it in the cloud
(an Azure Container Apps Job fed by a Storage queue), and the match joins their profile.

``store``   where uploads, jobs, results and models live (Azure Blob + Queue, or a local folder); the shared contract
"""
