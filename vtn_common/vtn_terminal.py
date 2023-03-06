import socket

TERMINAL = None
TERMINAL_PROMPT = 'monitor >>> '

class Netcat:
    ''' 
    Python "netcat like" module.
    Based on: https://gist.github.com/leonjza/f35a7252babdf77c8421
    '''

    def __init__(self, ip, port):
        self.buff = ''
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((ip, port))

    def write(self, data):
        self.socket.send(data)

    def read_until(self, data):
        '''
        Read data into the buffer until we have data 
        '''
        while not data in self.buff:
            self.buff += self.socket.recv(1024).decode('utf-8')
 
        pos = self.buff.find(data)
        rval = self.buff[:pos + len(data)]
        self.buff = self.buff[pos + len(data):]
 
        return rval
 
def _cmd(str_cmd):
    TERMINAL.write(bytes(str_cmd + '\n', 'utf-8'))
    ret = TERMINAL.read_until(TERMINAL_PROMPT)
    print(ret.rstrip(TERMINAL_PROMPT))

def ps():
    _cmd('ps')

def cancel(task_id):
    _cmd(f'cancel {task_id}')

def where(task_id):
    _cmd(f'where {task_id}')

def lld():
    log_level_debug()

def log_level_debug():
    _cmd('lld')

def lli():
    log_level_info()

def log_level_info():
    _cmd('lli')

def ase(ven_id):
    add_single_event(ven_id)

def add_single_event(ven_id):
    _cmd(f'ase {ven_id}')

def ape(ven_id, period):
    add_periodic_event(period, ven_id)

def add_periodic_event(ven_id, period):
    _cmd(f'ape {ven_id} {period}')

def start_terminal(port=5001):
    global TERMINAL
    TERMINAL = Netcat('localhost', port)
    TERMINAL.read_until(TERMINAL_PROMPT)
