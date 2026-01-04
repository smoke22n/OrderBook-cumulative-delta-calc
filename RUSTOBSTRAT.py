import sqlite3
import time
import logging
from freqtrade.strategy import IStrategy
from pandas import DataFrame
from datetime import datetime

logger = logging.getLogger(__name__)

class RustOrderbookStrategy(IStrategy):
    INTERFACE_VERSION = 3

    # --- CONFIGURAZIONE STRATEGIA ---
    minimal_roi = {"0": 0.1, "5": 0.05} 
    stoploss = -0.2
    timeframe = '1m'
    
    # FONDAMENTALE: Reattività immediata
    process_only_new_candles = False
    
    can_short = True

    # Path del DB visto da dentro il container Freqtrade
    DB_PATH = "/freqtrade/user_data/orderbook_cache.db"
    
    def leverage(self,pair: str,current_time: datetime,current_rate: float,proposed_leverage: float,max_leverage: float,entry_tag: str | None,side: str,**kwargs) -> float:
        return 12

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Freqtrade vuole almeno una colonna popolata
        dataframe['dummy'] = 0
        return dataframe

    def get_imbalance(self, current_pair):
        """
        1. Prende la coppia attuale (es. BTC/USDC:USDC)
        2. Trova il nome della moneta (BTC)
        3. Cerca nel DB i dati della liquidità USDT (BTC/USDT)
        """
        try:
            # Logica di Mapping:
            # Input: BTC/USDC:USDC oppure BTC/USDC
            # Step 1: Prendi "BTC"
            coin_name = current_pair.split('/')[0]
            
            # Step 2: Costruisci la chiave per il DB (dove salviamo sempre COIN/USDT)
            target_key = f"{coin_name}/USDT"

            conn = sqlite3.connect(self.DB_PATH, timeout=0.1)
            cursor = conn.cursor()
            cursor.execute("SELECT imbalance, updated_at FROM orderbook_metrics WHERE symbol=?", (target_key,))
            row = cursor.fetchone()
            conn.close()

            if row:
                imbalance = row[0]
                updated_at = row[1]
                
                # Se i dati sono vecchi di 10 secondi, Rust potrebbe essere fermo -> Ignora
                if time.time() - updated_at > 10:
                    return None
                
                return imbalance
            return None

        except Exception as e:
            return None

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if self.config['runmode'].value in ('live', 'dry_run'):
            
            imbalance = self.get_imbalance(metadata['pair'])
            
            if imbalance is not None:
                # Sbilanciamento Positivo -> Tanti Buy Limit -> Pressione Rialzista
                if imbalance > 0.85:
                    dataframe.loc[dataframe.index[-1], 'enter_long'] = 1
                    logger.info(f"RUST-SIG: {metadata['pair']} (Dati USDT) Imbalance {imbalance:.2f} -> LONG")
                
                # Sbilanciamento Negativo -> Tanti Sell Limit -> Pressione Ribassista
                elif imbalance < -0.85:
                    dataframe.loc[dataframe.index[-1], 'enter_short'] = 1
                    logger.info(f"RUST-SIG: {metadata['pair']} (Dati USDT) Imbalance {imbalance:.2f} -> SHORT")
        
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Uscita basata sull'inversione del flusso
        if self.config['runmode'].value in ('live', 'dry_run'):
            imbalance = self.get_imbalance(metadata['pair'])
            
            if imbalance is not None:
                # Se siamo Long ma l'imbalance crolla a favore dei venditori -> ESCI
                if imbalance < -0.2:
                    dataframe.loc[dataframe.index[-1], 'exit_long'] = 0
                
                # Se siamo Short ma l'imbalance schizza a favore dei compratori -> ESCI
                if imbalance > 0.2:
                    dataframe.loc[dataframe.index[-1], 'exit_short'] = 0
                    
        return dataframe