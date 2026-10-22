# Setting up Regista's Azure environment

The runbook for a new subscription: from an empty account to the live app with every feature, in about two hours.
It was written on 2026-10-21, when the first environment became unreachable. **Read "What went wrong last time"
first**: it is why the steps below are in this order.

## What went wrong last time

The first subscription was a free trial under a personal Microsoft account (a gmail address). In its own directory
that account counts as *external*, so its sign-ins carry only one factor, and when Azure began requiring two-step
verification for command-line tools, security defaults blocked the Azure CLI (error `AADSTS530035`). Trying to fix
that with "Convert to internal user" turned the account into a directory-owned one with a generated password that was
never saved. It was the directory's only administrator, so nobody could reset it. The live app kept running (it signs
in with its own identity), but nothing could be deployed or managed.

So: the command line signs in as an account that belongs to the directory, with Microsoft Authenticator; there are two
administrators; and nothing here ever uses "Convert to internal user".

## 1. Accounts (a person, about 30 minutes)

1. **A Microsoft account just for Azure** (for example a new Outlook.com address). Add a recovery phone and email,
   turn on **two-step verification** (account.microsoft.com/security > Advanced security options), and store the
   password in a password manager.
2. **Sign up for Azure pay-as-you-go** with it (or Azure for Students, if eligible). This creates a directory and a
   subscription.
3. **In-directory admin**, used for everything below. Azure portal > Microsoft Entra ID > Users > New user >
   Create new user: `admin@<directory>.onmicrosoft.com`. Then:
   - Entra ID > Roles and administrators > **Global Administrator** > Add assignment > this user.
   - Subscriptions > the new subscription > Access control (IAM) > Add role assignment > **Owner** > this user.
   - Sign in once as this user in a private window, change the password, and register **Microsoft Authenticator**.
4. **Emergency admin**, the same way (`breakglass@<directory>.onmicrosoft.com`, Global Administrator). Store its
   password offline and do not use it day to day. It exists so one lost password never locks the directory again.
5. Never use **"Convert to internal user"** on an account.

Keep the old personal account for GitHub and the hackathon platform; it plays no part in Azure.

## 2. Sign in and check (before anything is created)

```bash
az logout
az login --tenant <new tenant id> --use-device-code     # as admin@<directory>.onmicrosoft.com
az account set --subscription <new subscription id>
az account get-access-token --scope https://management.azure.com/.default --query expiresOn -o tsv
az account get-access-token --scope https://ai.azure.com/.default --query expiresOn -o tsv
```

Both token commands must print a date. `provision.sh` checks the same again and refuses an external (`#EXT#`)
account. Keep the old `.env` outside the repository (it belongs to the old environment).

## 3. Provision (about 20 minutes)

```bash
SUBSCRIPTION="<name or id>" LOCATION=<region> BUDGET_EMAIL=<your email> ./infra/provision.sh
```

`SUBSCRIPTION` is required: the script never uses the CLI's default, because a directory can hold subscriptions
that are not yours (a university's, for one). `LOCATION` is used for every resource unless `COSMOS_LOCATION` or
`SEARCH_LOCATION` is set. The script refuses a `.env` written for another subscription, and finds the GitHub
deploy identity only among app registrations you own, so it is safe in a shared directory.

**Azure for Students (Northeastern, 2026-10-21).** The subscription sits in the university's directory, where the
student account is an ordinary member with two-step verification (so the command line works) and Owner of the
subscription. A policy allows only `francecentral`, `germanywestcentral`, `canadacentral`, `denmarkeast` and
`belgiumcentral`; `gpt-5-mini` (GlobalStandard) is offered in France Central and Germany West Central. Students may
register apps, so the federated deploy identity works. Budgets may not be supported on the offer; it stops at its
credit limit instead, and the script warns and goes on. Step 1 (new accounts and admins) does not apply: the
directory belongs to the university.

```bash
SUBSCRIPTION="Azure for Students" LOCATION=francecentral BUDGET_EMAIL=<your email> ./infra/provision.sh
```

One run creates, in order: sign-in and quota checks (nothing is created if the model has no quota); Foundry with the
project and the `gpt-5-mini` deployment; Cosmos DB serverless in East US 2 with its four containers; Azure AI Search
(free tier, South Central US); key login switched off on both (Entra ID only); the Container Apps environment;
Application Insights on its Log Analytics workspace (capped at 0.1 GB a day) and connected to the Foundry project for
tracing; the container registry with no admin user; the GitHub Actions deploy identity (federated, no secret) and the
repository variables the workflow reads; a $60 monthly budget with email alerts; and `.env`.

If the model has no quota in East US: `LOCATION=eastus2 ./infra/provision.sh`, or request quota in the Foundry portal
(Management center > Quota). The model is a single setting (`MODEL=`), and the code reads it from `.env`.

Found on the second setup (2026-10-21) and handled by the scripts now: newer CLI extensions create "express"
Container Apps environments, which cannot pull with the app's identity (the script asks for workload profiles mode);
the Cosmos DB preview extension wants `--capacity-mode Serverless`; GitHub may sign workflow tokens with a subject that
carries the owner and repository ids (the script trusts both formats).

## 4. First deploy

1. Push to `main` (or run the workflow by hand). GitHub Actions runs the tests, builds the image, smoke-tests the agent
   tools inside it, and pushes it. The deploy job skips itself until the app exists.
2. Create the app once, with the image just pushed:

   ```bash
   IMAGE=<ACR_LOGIN_SERVER from .env>/regista:<commit sha> ./infra/deploy-app.sh
   ```

   It starts the app on a public placeholder, gives it its identity and roles (pull from the registry, Foundry, Cosmos
   DB, Search), waits a minute for the roles to apply, switches to our image with the write token and tracing secrets,
   waits until the new revision is the ready one, and writes `REGISTA_APP_URL` to `.env`.
3. From then on every push to `main` deploys itself. Run `deploy-app.sh` again only to change secrets or settings.

## 4b. The Player view's vision job

```bash
python -m regista.player.models push          # or: az storage blob upload-batch -d models --destination-path vision -s models/vision --auth-mode login
./infra/deploy-job.sh                         # the event-driven Container Apps Job on the vision-jobs queue
```

Run `deploy-app.sh` again after provisioning storage, so the app gets `REGISTA_STORAGE_ACCOUNT` and its storage roles.

## 5. Restore the library

```bash
./infra/restore-library.sh
```

Regenerates the library matches from their seeds (141 and 142; the generator is deterministic) and uploads them
through the live app's token-protected workflow, so Foundry labels them, Cosmos DB stores them and Search indexes them.
The committed sample match (`syn_0294`) ships inside the image. There were no real reviewer verdicts to restore.

## 6. Verify (read-only, except the restore above)

- `GET /api/health`: `librarian` is `foundry:gpt-5-mini`; `azure_mcp`, `tracing`, Cosmos DB and Search all true.
- `GET /api/matches`: `syn_0294`, `syn_0141`, `syn_0142`.
- **Ask Foundry** on the live app: answered by Foundry, with `search_index_query` among the tools (the Azure MCP Server
  running inside the container).
- **Chat with the Foundry engine**: a two-turn conversation answered by Foundry.
- Application Insights: spans from the container (`invoke_agent regista-librarian`, `chat gpt-5-mini`,
  `execute_tool search_index_query`) within a few minutes.
- Cosmos DB: three matches; AI Search: documents for the two uploaded matches.
- The viewer's Chat, Ask Foundry and Who's who panels load; writes ask for the token.

## 7. Afterwards

- Update the docs that name the old environment (README, CLAUDE.md §4.1, docs/architecture.md, docs/gap-analysis.md):
  the new URL, resource names and revision. The old app may keep serving an older version until its trial ends (about
  2026-11-19); nothing should link to it.
- Remove the old registry secrets from GitHub: `gh secret delete ACR_LOGIN_SERVER`, `ACR_USERNAME`, `ACR_PASSWORD`.
- After judging (2026-11-10): `./infra/provision.sh --destroy` (it also deletes the GitHub deploy identity).
