import socket

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
 
TERMINAL = None
TERMINAL_PROMPT = 'monitor >>> '

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

def pse(ven_id=None):
    push_single_event(ven_id)

def push_single_event(ven_id=None):
    if ven_id:
        _cmd(f'pse {ven_id}')
    else:
        _cmd('pse')

def ppe(period, ven_id=None):
    push_periodic_event(period, ven_id)

def push_periodic_event(period, ven_id=None):
    if ven_id:
        _cmd(f'ppe {period} {ven_id}')
    else:
        _cmd(f'ppe {period}')

TERMINAL = Netcat('localhost', 5000)
TERMINAL.read_until(TERMINAL_PROMPT)
