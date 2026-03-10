import threading
import time
from pymodbus.client import ModbusTcpClient


class ModbusButton:
    """
    Polls a single discrete input or coil on a Modbus TCP device and fires
    an on_press callback on a rising edge (False → True transition).

    Also exposes write_result() to drive 3 output coils (Y0/Y1/Y2) based on
    the inspection outcome — only the active coil is ON, the others are reset.

    Designed for Mitsubishi FX5U PLCs (Modbus TCP server on port 502):
      - Button input : X0 (IN 0) → discrete input address 0
      - Result output: Y0=NA, Y1=Pass, Y2=Fail (coil addresses 0, 1, 2)
    Reconnects automatically if the PLC drops the connection.
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
        self.host          = host
        self.port          = port
        self.address       = address
        self.unit          = unit
        self.use_coil      = use_coil
        self.poll_interval = poll_interval
        self.on_press: callable = None

        self._client: ModbusTcpClient | None = None
        self._thread: threading.Thread | None = None
        self._stop_event  = threading.Event()
        self._last_state  = False

    def connect(self):
        self._client = ModbusTcpClient(self.host, port=self.port, timeout=2)
        if not self._client.connect():
            raise ConnectionError(f"Cannot connect to Modbus device at {self.host}:{self.port}")
        print(f"Modbus connected: {self.host}:{self.port} "
              f"({'coil' if self.use_coil else 'discrete input'} #{self.address})")

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self._client:
            self._client.close()
        print("Modbus disconnected.")

    def write_result(self, start_address: int, value: int):
        """
        Write inspection result to 3 output coils (FC15).
        Exactly one coil at (start_address + value) is turned ON; the rest OFF.
          value=0 (NA)   → Y0=ON,  Y1=OFF, Y2=OFF
          value=1 (Pass) → Y0=OFF, Y1=ON,  Y2=OFF
          value=2 (Fail) → Y0=OFF, Y1=OFF, Y2=ON
        """
        coils = [False, False, False]
        coils[value] = True
        labels = {0: "NA", 1: "Pass", 2: "Fail"}

        for attempt in range(2):
            try:
                result = self._client.write_coils(start_address, coils)
                if result.isError():
                    print(f"Modbus write error: {result}")
                else:
                    print(f"Modbus output: Y{start_address + value} ON  "
                          f"({labels[value]}, Y{start_address}..Y{start_address + 2}"
                          f" = {[int(b) for b in coils]})")
                return
            except Exception as e:
                if attempt == 0:
                    print(f"Modbus write failed ({e}), reconnecting...")
                    self._reconnect()
                else:
                    print(f"Modbus write failed after reconnect: {e}")

    def _reconnect(self) -> bool:
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

    def _read_state(self) -> bool | None:
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
        while not self._stop_event.is_set():
            state = self._read_state()

            if state is None:
                print("Modbus connection lost, reconnecting...")
                while not self._stop_event.is_set():
                    if self._reconnect():
                        break
                    time.sleep(1.0)
                continue

            if state and not self._last_state:
                if callable(self.on_press):
                    self.on_press()

            self._last_state = state
            time.sleep(self.poll_interval)
