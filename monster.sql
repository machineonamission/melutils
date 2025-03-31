SELECT *,
       (SELECT SUM(points)
        FROM warnings
        WHERE (warn_timespan = 0 OR (:now - warn_timespan) < warnings.issuedat)
          AND warnings.server = :guild
          AND user = :user
          AND deactivated = 0) pointstotal
FROM auto_punishment
WHERE pointstotal >= warn_count
  AND warn_count > (pointstotal - :pointsjustgained)
  AND guild = :guild
ORDER BY punishment_duration, punishment_type DESC
LIMIT 1