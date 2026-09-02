SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE media (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  slug VARCHAR(190) NOT NULL UNIQUE,
  title VARCHAR(255) NOT NULL,
  title_de VARCHAR(255) NULL,
  title_en VARCHAR(255) NULL,
  original_title VARCHAR(512) NULL,
  original_language VARCHAR(16) NULL,
  media_type ENUM('movie','series','season','episode') NOT NULL,
  parent_id BIGINT UNSIGNED NULL,
  year SMALLINT UNSIGNED NULL,
  release_date DATE NULL,
  runtime_minutes SMALLINT UNSIGNED NULL,
  episode_count SMALLINT UNSIGNED NULL,
  season_count SMALLINT UNSIGNED NULL,
  media_status ENUM('unknown','upcoming','ongoing','ended','cancelled') NOT NULL DEFAULT 'unknown',
  synopsis TEXT NULL,
  studio VARCHAR(255) NULL,
  director VARCHAR(255) NULL,
  poster_url TEXT NULL,
  trailer_url TEXT NULL,
  imdb_id VARCHAR(32) NULL,
  tmdb_id BIGINT UNSIGNED NULL,
  imdb_rating DECIMAL(3,1) NULL,
  popularity_score DECIMAL(8,3) NULL,
  german_available TINYINT(1) NOT NULL DEFAULT 0,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_media_type (media_type),
  KEY idx_media_parent (parent_id),
  KEY idx_media_year (year),
  CONSTRAINT fk_media_parent FOREIGN KEY (parent_id) REFERENCES media(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE genres (
  id SMALLINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  slug VARCHAR(100) NOT NULL UNIQUE,
  name VARCHAR(100) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE media_genres (
  media_id BIGINT UNSIGNED NOT NULL,
  genre_id SMALLINT UNSIGNED NOT NULL,
  PRIMARY KEY (media_id,genre_id),
  FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE,
  FOREIGN KEY (genre_id) REFERENCES genres(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE providers (
  id SMALLINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  slug VARCHAR(64) NOT NULL UNIQUE,
  name VARCHAR(120) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE media_availability (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  media_id BIGINT UNSIGNED NOT NULL,
  provider_id SMALLINT UNSIGNED NOT NULL,
  country_code CHAR(2) NOT NULL DEFAULT 'DE',
  offer_type ENUM('subscription','ads','free','rent','buy') NOT NULL DEFAULT 'subscription',
  added_at DATE NULL,
  removed_at DATE NULL,
  web_url TEXT NULL,
  deeplink_url TEXT NULL,
  last_checked_at DATETIME NULL,
  UNIQUE KEY uq_availability (media_id,provider_id,country_code,offer_type),
  FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE,
  FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE provider_external_ids (
  provider_id SMALLINT UNSIGNED NOT NULL,
  source VARCHAR(32) NOT NULL,
  external_id VARCHAR(128) NOT NULL,
  external_name VARCHAR(255) NULL,
  last_checked_at DATETIME NULL,
  PRIMARY KEY(provider_id,source),
  UNIQUE KEY uq_provider_external(source,external_id),
  FOREIGN KEY(provider_id) REFERENCES providers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE media_external_ids (
  media_id BIGINT UNSIGNED NOT NULL,
  source VARCHAR(32) NOT NULL,
  external_id VARCHAR(128) NOT NULL,
  canonical_url TEXT NULL,
  last_checked_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (media_id,source),
  UNIQUE KEY uq_external_identity (source,external_id),
  KEY idx_external_media (media_id),
  FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE media_titles (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  media_id BIGINT UNSIGNED NOT NULL,
  language_code VARCHAR(16) NULL,
  title_type ENUM('display','original','alternative','short') NOT NULL DEFAULT 'alternative',
  title VARCHAR(512) NOT NULL,
  is_primary TINYINT(1) NOT NULL DEFAULT 0,
  source VARCHAR(32) NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_media_title (media_id,language_code,title_type,title),
  KEY idx_titles_media (media_id),
  FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE media_assets (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  media_id BIGINT UNSIGNED NOT NULL,
  asset_type ENUM('poster','backdrop','logo','still') NOT NULL,
  language_code VARCHAR(16) NULL,
  url TEXT NOT NULL,
  width SMALLINT UNSIGNED NULL,
  height SMALLINT UNSIGNED NULL,
  source VARCHAR(32) NULL,
  external_key VARCHAR(255) NULL,
  is_primary TINYINT(1) NOT NULL DEFAULT 0,
  sort_order SMALLINT UNSIGNED NOT NULL DEFAULT 100,
  last_checked_at DATETIME NULL,
  removed_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_assets_media_type (media_id,asset_type,removed_at,is_primary,sort_order),
  FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE media_source_records (
  media_id BIGINT UNSIGNED NOT NULL,
  source VARCHAR(32) NOT NULL,
  source_record_id VARCHAR(128) NULL,
  payload_hash CHAR(64) NULL,
  imported_at DATETIME NULL,
  last_checked_at DATETIME NULL,
  source_updated_at DATETIME NULL,
  status ENUM('active','missing','removed','error') NOT NULL DEFAULT 'active',
  PRIMARY KEY (media_id,source),
  FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE media_availability_reconcile (
  media_id BIGINT UNSIGNED NOT NULL,
  provider_id SMALLINT UNSIGNED NOT NULL,
  country_code CHAR(2) NOT NULL DEFAULT 'DE',
  offer_type ENUM('subscription','ads','free','rent','buy') NOT NULL,
  source VARCHAR(32) NOT NULL DEFAULT 'tmdb-watch',
  status ENUM('confirmed','new','suspect','remove_ready','uncheckable') NOT NULL DEFAULT 'confirmed',
  consecutive_misses SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  first_seen_at DATETIME NULL,
  last_seen_at DATETIME NULL,
  last_checked_at DATETIME NOT NULL,
  external_url TEXT NULL,
  live_provider_name VARCHAR(255) NULL,
  note VARCHAR(512) NULL,
  PRIMARY KEY(media_id,provider_id,country_code,offer_type,source),
  KEY idx_av_reconcile_status(status,last_checked_at),
  KEY idx_av_reconcile_provider(provider_id,status),
  FOREIGN KEY(media_id) REFERENCES media(id) ON DELETE CASCADE,
  FOREIGN KEY(provider_id) REFERENCES providers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
