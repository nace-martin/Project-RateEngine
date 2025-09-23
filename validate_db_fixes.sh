#!/bin/bash
# validate_db_fixes.sh
# Script to validate the DB fixes for RateEngine v2

echo "=== Validating RateEngine v2 DB Fixes ==="

# Check if psql is available
if ! command -v psql &> /dev/null
then
    echo "psql could not be found. Please ensure PostgreSQL client tools are installed."
    exit 1
fi

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo "DATABASE_URL is not set. Please set it to your PostgreSQL database connection string."
    exit 1
fi

echo "Running verification script..."
psql $DATABASE_URL -f verify_db_reform_v2.sql

echo "=== Validation Complete ==="