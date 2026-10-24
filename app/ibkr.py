"""Read-only historical data adapter. Never calls placeOrder()."""
from datetime import datetime
from threading import Event, Thread, Lock
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract

class HistoricalClient(EWrapper,EClient):
    def __init__(self):
        EClient.__init__(self,self)
        self.ready=Event(); self.finished=Event(); self.rows=[]; self.errors=[]
        self._request_id=None; self._lock=Lock()
    def nextValidId(self,orderId):
        self.ready.set()
    def historicalData(self,reqId,bar):
        if reqId==self._request_id:
            self.rows.append({'day':bar.date,'open':bar.open,'high':bar.high,'low':bar.low,'close':bar.close,'volume':bar.volume})
    def historicalDataEnd(self,reqId,start,end):
        if reqId==self._request_id: self.finished.set()
    def error(self,reqId,errorCode,errorString,advancedOrderRejectJson=''):
        if errorCode not in (2104,2106,2158,2107,2108):
            self.errors.append({'code':errorCode,'message':errorString})
            if reqId==self._request_id or reqId==-1: self.finished.set()

def fetch_daily(symbol:str, exchange='SMART',currency='USD',primary_exchange='',sec_type='STK',duration='1 Y',host='127.0.0.1',port=4002,client_id=31,timeout=45):
    client=HistoricalClient()
    try:
        client.connect(host,port,client_id)
        worker=Thread(target=client.run,daemon=True); worker.start()
        if not client.ready.wait(timeout=10): raise TimeoutError('IBKR connection handshake timed out')
        contract=Contract(); contract.symbol=symbol; contract.secType=sec_type; contract.exchange=exchange; contract.currency=currency
        if primary_exchange: contract.primaryExchange=primary_exchange
        client._request_id=1001
        client.reqHistoricalData(1001,contract,'',duration,'1 day','TRADES',1,1,False,[])
        if not client.finished.wait(timeout=timeout):
            client.cancelHistoricalData(1001)
            raise TimeoutError('IBKR historical data request timed out')
        if client.errors: raise RuntimeError(f'IBKR errors: {client.errors}')
        if not client.rows: raise ValueError('IBKR returned no bars; check contract and subscriptions')
        return client.rows
    finally:
        if client.isConnected(): client.disconnect()
