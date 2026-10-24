from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = 'sqlite:///./market.db'
    ibkr_host: str = '127.0.0.1'
    ibkr_port: int = 4002  # IB Gateway paper; TWS paper often 7497
    ibkr_client_id: int = 31
    api_token: str = 'change-me'
    sec_user_agent: str = ''
    enable_scheduler: bool = False
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

settings = Settings()
