var ActiveUsersCompare = {
  // differences are only given for points of at least this many contacts, as in the compare command
  MIN_COUNT: 100,

  // the point furthest from the activity tables, as { value, name, key }
  largestDifference: function (existing, hll) {
    var largest = null;
    existing.forEach(function (series) {
      var other = hll.filter(function (s) { return s.name === series.name; })[0];
      Object.keys(series.data).forEach(function (key) {
        var count = series.data[key];
        if (other && count >= ActiveUsersCompare.MIN_COUNT && key in other.data) {
          var value = (other.data[key] - count) / count;
          if (largest === null || Math.abs(value) > Math.abs(largest.value)) {
            largest = { value: value, name: series.name, key: key, existing: count, hll: other.data[key] };
          }
        }
      });
    });
    return largest;
  }
};
