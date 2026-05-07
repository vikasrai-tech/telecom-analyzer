# Setup Guide — Windows + WSL2 + 16 GB RAM

This guide takes you from a fresh Windows machine to a running
walking-skeleton dashboard in approximately **2-3 hours**.
Follow steps in order.

---

## Step 1: Install WSL2 with Ubuntu 22.04

Open **PowerShell as Administrator** and run:

```powershell
wsl --install -d Ubuntu-22.04
```

Reboot when prompted. After reboot, Ubuntu opens automatically.
Set a Linux username and password (remember the password — you will
need it for `sudo`).

Verify version:

```powershell
wsl --list --verbose
```

It must show `VERSION 2`. If it shows 1, run `wsl --set-version Ubuntu-22.04 2`.

---

## Step 2: Configure WSL2 memory limit

By default WSL2 takes up to 50% of your RAM, which is 8 GB on a 16 GB
machine. We need 12 GB to run the LLM comfortably.

In **Windows** (not WSL), open `C:\Users\<your-name>\.wslconfig`
(create the file if it does not exist) and paste:

```ini
[wsl2]
memory=12GB
processors=6
swap=4GB
localhostForwarding=true
```

Then in PowerShell:

```powershell
wsl --shutdown
```

Reopen Ubuntu. Verify with `free -h` inside Ubuntu — you should see ~12 GB.

---

## Step 3: Update Ubuntu and install system tools

Inside the **Ubuntu terminal**:

```bash
sudo apt update && sudo apt upgrade -y

sudo apt install -y \
  build-essential git curl wget unzip \
  tshark wireshark-common \
  python3-pip python3-venv \
  graphviz pkg-config \
  libcap2-bin

# Allow tshark to capture without sudo (one-time)
sudo dpkg-reconfigure wireshark-common
sudo usermod -a -G wireshark $USER
sudo setcap 'CAP_NET_RAW+eip CAP_NET_ADMIN+eip' $(which dumpcap)
```

Log out and back in (`exit`, then reopen Ubuntu) so group changes apply.

Verify:
```bash
tshark --version
```

---

## Step 4: Install Miniconda (Python environment manager)

```bash
cd ~
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh -b -p $HOME/miniconda3
~/miniconda3/bin/conda init bash
source ~/.bashrc
```

Verify: `conda --version`

---

## Step 5: Install Docker Desktop

Install **Docker Desktop for Windows** from docker.com.
During installation, enable **WSL2 integration** for Ubuntu-22.04.

Verify in Ubuntu:
```bash
docker --version
docker run hello-world
```

---

## Step 6: Install Ollama (local LLM runtime)

Inside Ubuntu:
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Pull Phi-3 Mini (this downloads ~2.3 GB):
```bash
ollama pull phi3:mini
```

Test it:
```bash
ollama run phi3:mini "What is NGAP in 5G?"
```

You should get a coherent answer in 10-30 seconds. Press Ctrl+D to exit.

---

## Step 7: Install VS Code with WSL extension

1. Install **VS Code** on **Windows** (not WSL).
2. Open VS Code → Extensions → install **"WSL"** by Microsoft.
3. Press `F1` → "WSL: Connect to WSL" → choose Ubuntu-22.04.
4. Inside WSL VS Code, install: **Python**, **Pylance**, **Black Formatter**,
   **GitLens**, **Even Better TOML**.

---

## Step 8: Clone and set up the project

```bash
cd ~
mkdir -p projects && cd projects
git clone <your-github-repo-url> telecom-analyzer
cd telecom-analyzer

# Create conda environment
conda create -n telecom python=3.11 -y
conda activate telecom

# Install dependencies
pip install -r requirements.txt

# Install pre-commit hooks
pre-commit install
```

Open the project in VS Code:
```bash
code .
```

VS Code should pick up the conda environment automatically.
If not: `Ctrl+Shift+P` → "Python: Select Interpreter" → choose `telecom`.

---

## Step 9: Run the walking skeleton

```bash
streamlit run src/dashboard/app.py
```

Open `http://localhost:8501` in your **Windows browser** (WSL2 forwards
the port automatically). You should see the dashboard.

Upload any small PCAP file to verify the pipeline works end-to-end.

---

## Step 10: First commit

```bash
git add .
git commit -m "chore: initial setup, walking skeleton runs"
git push origin main
```

---

## Troubleshooting

**WSL2 takes too much memory even when idle:**
Run `wsl --shutdown` in PowerShell when not coding.

**`tshark` permission denied:**
Re-run Step 3 group commands. Logout/login required.

**Streamlit not opening on Windows browser:**
Try `http://localhost:8501` first; if that fails, check WSL IP with
`ip addr show eth0` and use that IP.

**Ollama slow on first call:**
First call loads the model into RAM (~30s). Subsequent calls are fast.

**Python imports fail in VS Code but work in terminal:**
VS Code is using the wrong interpreter. `Ctrl+Shift+P` → "Python: Select Interpreter".

---

## What's next

Once setup is verified, follow `docs/WEEK_1_GUIDE.md` to start
implementing the walking skeleton enhancements.
