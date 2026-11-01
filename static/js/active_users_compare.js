var ActiveUsersCompare = {
  // differences are only given for points where either side has at least this many contacts, as a handful of contacts
  // makes for large relative differences that mean nothing
  MIN_COUNT: 100,

  // what a series is of, as in the compare command, as boundaries of an org can share a name
  seriesKey: function (series) {
    return series.osm_id || series.name;
  },

  // the point furthest from the activity tables, as { value, name, key }
  largestDifference: function (existing, hll) {
    var largest = null;
    existing.forEach(function (series) {
      var other = hll.filter(function (s) {
        return ActiveUsersCompare.seriesKey(s) === ActiveUsersCompare.seriesKey(series);
      })[0];
      var otherData = other ? other.data : {};
      Object.keys(series.data).forEach(function (key) {
        var count = series.data[key];
        var sketched = otherData[key] || 0;
        if (Math.max(count, sketched) >= ActiveUsersCompare.MIN_COUNT) {
          var value = (sketched - count) / Math.max(count, 1);
          if (largest === null || Math.abs(value) > Math.abs(largest.value)) {
            largest = { value: value, name: series.name, key: key, existing: count, hll: sketched };
          }
        }
      });
    });
    return largest;
  }
};
