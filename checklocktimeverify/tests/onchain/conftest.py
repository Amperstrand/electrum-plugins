import os
import time
import shutil
import subprocess
from pathlib import Path
import pytest

ELECTRUM_CLI = os.path.expanduser('/Users/macbook/src/electrum/venv/bin/electrum')
DEFAULT_WALLET = os.path.expanduser('~/.electrum/signet/wallets/default_wallet')


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


@pytest.fixture(scope='session')
def electrum_signet(tmp_path_factory):
    """Start an isolated Electrum signet daemon with a throwaway wallet.

    Yields the wallet path string.
    """
    # Allow opting in to using the existing system wallet (user wants that)
    use_system_wallet = os.environ.get('ELECTRUM_SYSTEM_WALLET', '').lower() in ('1', 'true', 'yes')
    requested_wallet = os.environ.get('ELECTRUM_WALLET_PATH')
    tmpdir = tmp_path_factory.mktemp('electrum_signet')
    wallet_dir = tmpdir / 'wallets'
    wallet_dir.mkdir(parents=True, exist_ok=True)
    wallet_path = str(wallet_dir / 'test_wallet')

    if use_system_wallet:
        # Prefer user-specified env var, else default signet wallet path
        wallet_path = str(Path(requested_wallet).expanduser()) if requested_wallet else DEFAULT_WALLET
        if not os.path.exists(wallet_path):
            pytest.skip(f"System wallet not found at {wallet_path}; set ELECTRUM_WALLET_PATH or create a wallet")

    created = False
    # Create wallet non-interactively only if not using system wallet
    create_cmd = [ELECTRUM_CLI, '--signet', '-D', str(tmpdir), '-w', wallet_path, 'create', '--seed_type', 'standard', '--password', '']
    if not use_system_wallet:
        res = _run(create_cmd)
    else:
        res = None
    if res and res.returncode != 0:
        # Try without explicit -w and let electrum choose a wallet file
        res2 = _run([ELECTRUM_CLI, '--signet', '-D', str(tmpdir), 'create', '--seed_type', 'standard', '--password', ''])
        if res2.returncode != 0:
            pytest.skip("Electrum CLI wallet creation failed; skipping RPC tests")
        # Find any wallet file
        wallets = list((tmpdir / 'wallets').glob('*'))
        if not wallets:
            pytest.skip('Could not create wallet; skipping RPC tests')
        wallet_path = str(wallets[0])

    # Start daemon. If using system wallet, don't pass -D (use its existing electrum dir)
    daemon_started_by_fixture = False
    if use_system_wallet:
        if os.path.exists(wallet_path):
            start_cmd = [ELECTRUM_CLI, '--signet', '-w', wallet_path, 'daemon', '-d']
        else:
            pytest.skip('System wallet path does not exist')
    else:
        start_cmd = [ELECTRUM_CLI, '--signet', '-D', str(tmpdir), '-w', wallet_path, 'daemon', '-d']
    res = _run(start_cmd)
    if res and res.returncode != 0 and ('already running' not in (res.stderr or '').lower()):
        pytest.skip('Cannot start Electrum daemon; skipping RPC tests')
    if res and res.returncode == 0:
        daemon_started_by_fixture = True

    # Wait for RPC to respond
    for _ in range(10):
        check_cmd = [ELECTRUM_CLI, '--signet', '-w', wallet_path, 'getinfo'] if use_system_wallet else [ELECTRUM_CLI, '--signet', '-D', str(tmpdir), '-w', wallet_path, 'getinfo']
        ok = _run(check_cmd)
        if ok.returncode == 0:
            break
        time.sleep(0.5)
    else:
        # Not responsive, but we'll still yield wallet_path for manual checks
        pytest.skip('Electrum daemon not responding to RPC; skipping RPC tests')

    yield wallet_path

    # Teardown: stop daemon (only if we started it) and remove directory
    if daemon_started_by_fixture:
        stop_cmd = [ELECTRUM_CLI, '--signet', '-w', wallet_path, 'stop'] if use_system_wallet else [ELECTRUM_CLI, '--signet', '-D', str(tmpdir), '-w', wallet_path, 'stop']
        _run(stop_cmd)
    try:
        shutil.rmtree(tmpdir)
    except Exception:
        pass
