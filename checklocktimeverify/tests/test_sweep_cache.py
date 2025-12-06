import types
import time
import sys

# ---- Minimal Electrum stubs so we can import the plugin without Electrum installed ----
electrum_mod = types.ModuleType('electrum')

plugin_mod = types.ModuleType('electrum.plugin')
class _BasePlugin:
    def __init__(self, parent, config, name):
        self.parent = parent
        self.config = config
        self.name = name
def _hook(func):
    return func
plugin_mod.BasePlugin = _BasePlugin
plugin_mod.hook = _hook

i18n_mod = types.ModuleType('electrum.i18n')
i18n_mod._ = lambda s: s

bitcoin_mod = types.ModuleType('electrum.bitcoin')
bitcoin_mod.address_to_scripthash = lambda addr: '00'*32

util_mod = types.ModuleType('electrum.util')
class _TxMinedInfo:
    def __init__(self, _height=0, conf=0, timestamp=None):
        self._height = _height
        self.conf = conf
        self.timestamp = timestamp
    def height(self):
        return 0 if self._height <= 0 else self._height
util_mod.TxMinedInfo = _TxMinedInfo

sys.modules['electrum'] = electrum_mod
sys.modules['electrum.plugin'] = plugin_mod
sys.modules['electrum.i18n'] = i18n_mod
sys.modules['electrum.bitcoin'] = bitcoin_mod
sys.modules['electrum.util'] = util_mod

from checklocktimeverify.qt import Plugin


class FakeTxMinedInfo:
    def __init__(self, h, conf, ts=None):
        self._height = h
        self.conf = conf
        self.timestamp = ts
    def height(self):
        return 0 if self._height <= 0 else self._height


class FakeTxOut:
    def __init__(self, address, value):
        self.address = address
        self.value = value


class FakeTx:
    def __init__(self, outputs=None, inputs=None):
        self._outputs = outputs or []
        self._inputs = inputs or []
    def outputs(self):
        return self._outputs
    def inputs(self):
        return self._inputs


class FakePrevout:
    def __init__(self, txid, out_idx):
        self.txid = bytes.fromhex(txid)
        self.out_idx = out_idx


class FakeTxIn:
    def __init__(self, prev_txid, prev_vout):
        self.prevout = FakePrevout(prev_txid, prev_vout)


class FakeADB:
    def __init__(self):
        self._history = {}
        self._txs = {}
        self._height = 200
        self.network = types.SimpleNamespace(get_local_height=lambda: self._height)
        self.get_tx_height_calls = 0

    def get_address_history(self, addr):
        return self._history.get(addr, {})

    def get_transaction(self, txid):
        return self._txs.get(txid)

    def get_tx_height(self, txid):
        self.get_tx_height_calls += 1
        # return confirmed height for the sweep tx, unconfirmed for others
        if txid == self._sweep_txid:
            return FakeTxMinedInfo(self._sweep_height, self._height - self._sweep_height + 1, int(time.time()))
        return FakeTxMinedInfo(0, 0, None)

    def get_local_height(self):
        return self._height


class FakeWallet:
    def __init__(self, adb):
        self.adb = adb
        self.network = adb.network
        self.db = types.SimpleNamespace(get_transaction=lambda txid: None)


def setup_fake_chain():
    adb = FakeADB()
    addr = "tb1qexampleaddr0000000000000000000000000000000000000"
    # prev funding tx that created a UTXO to addr
    prev_txid = "11" * 32
    prev_tx = FakeTx(outputs=[FakeTxOut(addr, 1234)])
    adb._txs[prev_txid] = prev_tx

    # sweep tx that spends that UTXO
    sweep_txid = "22" * 32
    sweep_tx = FakeTx(inputs=[FakeTxIn(prev_txid, 0)], outputs=[FakeTxOut("tb1qdest", 1000)])
    adb._txs[sweep_txid] = sweep_tx
    adb._history[addr] = {prev_txid: None, sweep_txid: None}
    adb._sweep_txid = sweep_txid
    adb._sweep_height = 150
    return addr, adb, sweep_txid


def test_sweep_cache_monotonic_conf():
    addr, adb, sweep_txid = setup_fake_chain()
    plugin = Plugin(None, types.SimpleNamespace(), "cltv")
    wallet = FakeWallet(adb)

    # First call: cache miss, scans history
    info1 = plugin.get_sweep_info(addr, wallet)
    assert info1 is not None
    assert info1["txid"] == sweep_txid
    calls_after_first = adb.get_tx_height_calls
    assert calls_after_first >= 1  # refreshed mined info

    # Second call: cache hit, should not rescan history, but refresh height via get_tx_height
    info2 = plugin.get_sweep_info(addr, wallet)
    assert info2["txid"] == sweep_txid
    calls_after_second = adb.get_tx_height_calls
    assert calls_after_second == calls_after_first + 1

    # Invalidate and ensure cache clears
    plugin._invalidate_sweep_cache_for_address(wallet, addr)
    info3 = plugin.get_sweep_info(addr, wallet)
    assert info3["txid"] == sweep_txid
    assert adb.get_tx_height_calls >= calls_after_second + 1


def test_cache_updates_confs():
    addr, adb, sweep_txid = setup_fake_chain()
    plugin = Plugin(None, types.SimpleNamespace(), "cltv")
    wallet = FakeWallet(adb)

    info = plugin.get_sweep_info(addr, wallet)
    initial_confs = info["confirmations"]
    # Advance chain height
    adb._height += 5
    info_updated = plugin.get_sweep_info(addr, wallet)
    assert info_updated["confirmations"] == initial_confs + 5
