use axum::{routing::post, Router};

fn app() -> Router {
    Router::new()
        .route("/ledger/entry", post(create_entry))
        .route("/internal/metrics", get(metrics))
}
