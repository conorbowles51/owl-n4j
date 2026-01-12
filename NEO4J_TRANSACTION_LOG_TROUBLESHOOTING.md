# Neo4j Transaction Log Error Troubleshooting Guide

## Error Description

The error `Neo.DatabaseError.Transaction.TransactionLogError` indicates that Neo4j cannot append a transaction to its transaction log. This is typically a server-side issue that requires attention on the Neo4j server.

## Common Causes

1. **Disk Space Issues**: The Neo4j transaction log directory may be full
2. **Transaction Log Corruption**: The transaction log files may be corrupted
3. **Too Many Concurrent Transactions**: The server may be overwhelmed with too many simultaneous transactions
4. **Neo4j Configuration Issues**: Transaction log settings may be misconfigured

## Immediate Actions

### 1. Check Disk Space

```bash
# Check disk space on the Neo4j server
df -h

# Check Neo4j data directory specifically
du -sh /path/to/neo4j/data/transactions
```

If disk space is low:
- Free up disk space
- Consider moving Neo4j data to a larger partition
- Clean up old transaction logs (see below)

### 2. Check Neo4j Logs

```bash
# View Neo4j logs for more details
tail -f /path/to/neo4j/logs/neo4j.log

# Or if using Docker
docker logs neo4j-container-name
```

### 3. Check Transaction Log Status

Connect to Neo4j and check transaction status:

```cypher
// Check current transaction status
CALL dbms.queryJmx("org.neo4j:instance=kernel#0,name=Transactions") YIELD attributes
RETURN attributes
```

## Solutions

### Solution 1: Free Up Disk Space

If disk space is the issue:

1. **Stop Neo4j** (if safe to do so)
2. **Clean up old transaction logs** (Neo4j keeps transaction logs for point-in-time recovery)
3. **Restart Neo4j**

**Warning**: Only clean transaction logs if you don't need point-in-time recovery. This should be done carefully.

### Solution 2: Increase Transaction Log Size

Edit `neo4j.conf`:

```properties
# Increase transaction log rotation size (default is 250M)
dbms.tx_log.rotation.retention_policy=1 days size
dbms.tx_log.rotation.size=500M
```

Then restart Neo4j.

### Solution 3: Check for Corrupted Logs

1. **Stop Neo4j**
2. **Check transaction log integrity**:
   ```bash
   # Neo4j has built-in tools to check log integrity
   # Check Neo4j documentation for your version
   ```
3. **If corrupted, restore from backup** or rebuild the database

### Solution 4: Reduce Transaction Load

The ingestion pipeline has been updated with retry logic, but you can also:

1. **Process documents in smaller batches**
2. **Reduce concurrent ingestion processes**
3. **Increase Neo4j memory settings** in `neo4j.conf`:
   ```properties
   dbms.memory.heap.initial_size=2g
   dbms.memory.heap.max_size=4g
   dbms.memory.pagecache.size=2g
   ```

## Application-Level Improvements

The ingestion pipeline has been updated with:

1. **Automatic Retry Logic**: Transient errors are automatically retried with exponential backoff
2. **Better Error Messages**: More detailed error information to help diagnose issues
3. **Transaction Error Handling**: Specific handling for transaction log errors

## Prevention

1. **Monitor Disk Space**: Set up alerts for low disk space
2. **Regular Backups**: Ensure regular backups are taken
3. **Transaction Log Rotation**: Configure appropriate log rotation policies
4. **Resource Monitoring**: Monitor Neo4j memory and CPU usage

## Neo4j Configuration Recommendations

For production environments, consider these settings in `neo4j.conf`:

```properties
# Transaction log settings
dbms.tx_log.rotation.retention_policy=7 days size
dbms.tx_log.rotation.size=500M

# Memory settings (adjust based on available RAM)
dbms.memory.heap.initial_size=2g
dbms.memory.heap.max_size=4g
dbms.memory.pagecache.size=2g

# Connection settings
dbms.connector.bolt.thread_pool_max_size=400
dbms.connector.http.thread_pool_max_size=200
```

## Getting Help

If the issue persists:

1. **Collect Neo4j logs**: `/path/to/neo4j/logs/neo4j.log`
2. **Collect system information**: Disk space, memory, CPU usage
3. **Note the exact error message and transaction ID**
4. **Check Neo4j community forums** or **Neo4j support**

## References

- [Neo4j Transaction Log Documentation](https://neo4j.com/docs/operations-manual/current/configuration/transaction-logs/)
- [Neo4j Troubleshooting Guide](https://neo4j.com/docs/operations-manual/current/troubleshooting/)
- [Neo4j Configuration Reference](https://neo4j.com/docs/operations-manual/current/configuration/)
