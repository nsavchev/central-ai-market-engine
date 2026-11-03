-- Operator-provided VPS DDL, 2026-11-03. No rows, roles or credentials.
-- Source schema archive SHA256:
-- 93926a2bdf58683017fa6a3b12c455c15f0f8b82fdf2fd88f69a1e489f97d48d
CREATE TABLE public.daily_bars (
 id integer NOT NULL, instrument_id integer NOT NULL, day date NOT NULL,
 open double precision NOT NULL, high double precision NOT NULL,
 low double precision NOT NULL, close double precision NOT NULL,
 volume double precision NOT NULL, source character varying(24) NOT NULL,
 fetched_at timestamp with time zone NOT NULL
);
CREATE TABLE public.financial_snapshots (
 id integer NOT NULL, symbol character varying(32) NOT NULL,
 period_end date NOT NULL, period_type character varying(8) NOT NULL,
 currency character varying(3) NOT NULL, source character varying(40) NOT NULL,
 payload json NOT NULL, imported_at timestamp with time zone NOT NULL
);
CREATE TABLE public.instruments (
 id integer NOT NULL, symbol character varying(32) NOT NULL,
 exchange character varying(32) NOT NULL, currency character varying(8) NOT NULL,
 sec_type character varying(12) NOT NULL, primary_exchange character varying(32) NOT NULL
);
CREATE TABLE public.paper_accounts (
 id integer NOT NULL, cash double precision NOT NULL,
 currency character varying(8) NOT NULL
);
CREATE TABLE public.paper_trades (
 id integer NOT NULL, account_id integer NOT NULL,
 symbol character varying(32) NOT NULL, side character varying(4) NOT NULL,
 quantity double precision NOT NULL, price double precision NOT NULL,
 fee double precision NOT NULL, executed_at timestamp with time zone NOT NULL
);
CREATE SEQUENCE public.daily_bars_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
CREATE SEQUENCE public.financial_snapshots_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
CREATE SEQUENCE public.instruments_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
CREATE SEQUENCE public.paper_accounts_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
CREATE SEQUENCE public.paper_trades_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.daily_bars_id_seq OWNED BY public.daily_bars.id;
ALTER SEQUENCE public.financial_snapshots_id_seq OWNED BY public.financial_snapshots.id;
ALTER SEQUENCE public.instruments_id_seq OWNED BY public.instruments.id;
ALTER SEQUENCE public.paper_accounts_id_seq OWNED BY public.paper_accounts.id;
ALTER SEQUENCE public.paper_trades_id_seq OWNED BY public.paper_trades.id;
ALTER TABLE ONLY public.daily_bars ALTER COLUMN id SET DEFAULT nextval('public.daily_bars_id_seq'::regclass);
ALTER TABLE ONLY public.financial_snapshots ALTER COLUMN id SET DEFAULT nextval('public.financial_snapshots_id_seq'::regclass);
ALTER TABLE ONLY public.instruments ALTER COLUMN id SET DEFAULT nextval('public.instruments_id_seq'::regclass);
ALTER TABLE ONLY public.paper_accounts ALTER COLUMN id SET DEFAULT nextval('public.paper_accounts_id_seq'::regclass);
ALTER TABLE ONLY public.paper_trades ALTER COLUMN id SET DEFAULT nextval('public.paper_trades_id_seq'::regclass);
ALTER TABLE ONLY public.daily_bars ADD CONSTRAINT daily_bars_instrument_id_day_source_key UNIQUE (instrument_id, day, source);
ALTER TABLE ONLY public.daily_bars ADD CONSTRAINT daily_bars_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.financial_snapshots ADD CONSTRAINT financial_snapshots_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.financial_snapshots ADD CONSTRAINT financial_snapshots_symbol_period_end_period_type_currency__key UNIQUE (symbol, period_end, period_type, currency, source);
ALTER TABLE ONLY public.instruments ADD CONSTRAINT instruments_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.instruments ADD CONSTRAINT instruments_symbol_exchange_currency_sec_type_primary_excha_key UNIQUE (symbol, exchange, currency, sec_type, primary_exchange);
ALTER TABLE ONLY public.paper_accounts ADD CONSTRAINT paper_accounts_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.paper_trades ADD CONSTRAINT paper_trades_pkey PRIMARY KEY (id);
CREATE INDEX ix_financial_snapshots_symbol ON public.financial_snapshots USING btree (symbol);
ALTER TABLE ONLY public.daily_bars ADD CONSTRAINT daily_bars_instrument_id_fkey FOREIGN KEY (instrument_id) REFERENCES public.instruments(id);
ALTER TABLE ONLY public.paper_trades ADD CONSTRAINT paper_trades_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.paper_accounts(id);
