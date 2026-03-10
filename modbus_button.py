import threading
import time
from pymodbus.client import ModbusTcpClient


class ModbusButton:
    """
    Polls a single discrete input or coil on a Modbus TCP device.
    Calls `on_press` callback on a rising edge (0 -> 1 transition).

    Designed for Mitsubishi FX5U PLCs:
      - IN 0 (X0) = discrete input address 0  (MODBUS_USE_COIL=false)
      - Reconnects automatically when the PLC drops the connection.
    """

    def __init__(
        self,
        host: str,
        port: int = 502,
        address: int = 0,
        unit: int = 1,
        use_coil: bool = False,
        poll_interval: float = 0.1,
    ):
        self.host = host
        self.port = port
        self.address = address
        self.unit = unit
        self.use_coil = use_coil
        self.poll_interval = poll_interval

        self._client: ModbusTcpClient | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_state: bool = False
        self.on_press: callable = None  # set by caller

    # ------------------------------------------------------------------ #
    # Connection management                                                #
    # ------------------------------------------------------------------ #

    def connect(self):
        self._client = ModbusTcpClient(self.host, port=self.port, timeout=2)
        if not self._client.connect():
            raise ConnectionError(
                f"Cannot connect to Modbus device at {self.host}:{self.port}"
            )
        print(f"Modbus connected: {self.host}:{self.port} "
              f"({'coil' if self.use_coil else 'discrete input'} #{self.address}, unit={self.unit})")

    def _reconnect(self) -> bool:
        """Try once to re-establish the TCP connection. Returns True on success."""
        try:
            if self._client:
                self._client.close()
            self._client = ModbusTcpClient(self.host, port=self.port, timeout=2)
            ok = self._client.connect()
            if ok:
                print(f"Modbus reconnected: {self.host}:{self.port}")
            return ok
        except Exception as e:
            print(f"Modbus reconnect failed: {e}")
            return False

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def start(self):
        """Start background polling thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop polling and close connection."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self._client:
            self._client.close()
        print("Modbus disconnected.")

    # ------------------------------------------------------------------ #
    # Reading                                                              #
    # ------------------------------------------------------------------ #

    def _read_state(self) -> bool | None:
        """
        Returns True/False for button state, or None on connection error
        (caller will trigger reconnect).
        """
        try:
            if self.use_coil:
                result = self._client.read_coils(self.address, count=1)
            else:
                result = self._client.read_discrete_inputs(self.address, count=1)

            if result.isError():
                return None
            return bool(result.bits[0])
        except Exception:
            return None

    def _poll_loop(self):
        reconnect_delay = 1.0  # seconds between reconnect attempts

        while not self._stop_event.is_set():
            state = self._read_state()

            if state is None:
                # Connection lost — reconnect and skip this cycle
                print("Modbus connection lost, reconnecting...")
                while not self._stop_event.is_set():
                    if self._reconnect():
                        break
                    time.sleep(reconnect_delay)
                continue

            # Rising edge: button just pressed
            if state and not self._last_state:
                if callable(self.on_press):
                    self.on_press()

            self._last_state = state
            time.sleep(self.poll_interval)
