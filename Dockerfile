FROM rust:slim-bullseye as builder

WORKDIR /usr/src
# Dipendenze necessarie per compilare openssl (native-tls)
RUN apt-get update && apt-get install -y pkg-config libssl-dev && rm -rf /var/lib/apt/lists/*
# Crea un progetto vuoto per ingannare Cargo e fargli scaricare le dipendenze
RUN cargo new rust_feeder
WORKDIR /usr/src/rust_feeder

# --- CORREZIONE QUI SOTTO ---
# Copiamo SOLO Cargo.toml (rimosso Cargo.lock)
COPY Cargo.toml ./

# Compila le dipendenze (questo genererà il Cargo.lock dentro il container)
RUN cargo build --release

# Ora cancella il main.rs finto creato da "cargo new" e copia il tuo codice vero
RUN rm src/*.rs
# --- CORREZIONE PERCORSO ---
# Assicurati che la cartella src esista nel tuo PC dentro rust_feeder
COPY src ./src

# Compila l'eseguibile finale
# Il touch serve a dire al compilatore "ehi, il file è cambiato, ricompila!"
RUN touch src/main.rs && cargo build --release

# --- FASE FINALE (Immagine leggera) ---
FROM debian:bullseye-slim
RUN apt-get update && apt-get install -y libssl-dev ca-certificates libsqlite3-0 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/src/rust_feeder/target/release/rust_feeder /usr/local/bin/rust_feeder

WORKDIR /data
CMD ["rust_feeder"]
