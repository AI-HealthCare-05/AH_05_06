from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `ocr_field_candidate` (
    `ocr_field_candidate_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `candidate_value` LONGTEXT NOT NULL,
    `confidence` DECIMAL(5,4),
    `rank` SMALLINT NOT NULL,
    `source_date` DATE,
    `is_selected` BOOL NOT NULL DEFAULT 0,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `ocr_field_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_ocr_field_c_ocr_fie_ede909` (`ocr_field_id`, `rank`),
    CONSTRAINT `fk_ocr_fiel_ocr_fiel_e2cf222c` FOREIGN KEY (`ocr_field_id`) REFERENCES `ocr_field` (`ocr_field_id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='A ranked alternative retained when one field has multiple readings.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `ocr_field_candidate`;"""


MODELS_STATE = (
    "eJztXV1z2jgX/isarvrOZLsNhSTNXhFCWrYEMoR0d7bpeIStgLfGZm05aWan//2V5A9sWT"
    "a2+bJZ3SQg68j2o6MjnUdHh38bC0tDhvO2g2xdnTcuwb8NEy4Q+cBdOQENuFyuymkBhlOD"
    "VYWrOlMH21DFpPQJGg4iRRpyVFtfYt0ySanpGgYttFRSUTdnqyLX1P9xkYKtGcJzZJMLX7"
    "+RYt3U0A/kBF+X35UnHRla7FF1jd6blSv4dcnK+ia+YRXp3aaKahnuwlxVXr7iuWWGtXUT"
    "09IZMpENMaLNY9ulj0+fzn/P4I28J11V8R4xIqOhJ+gaOPK6OTFQLZPiR57GYS84o3f5pX"
    "naOm9dvD9rXZAq7EnCkvOf3uut3t0TZAgMJ42f7DrE0KvBYFzh9oxshz5SArzuHNpi9CIi"
    "HITkwXkIA8CyMAwKViCuFGdLKC7gD8VA5gxTBW+22xmYfemMu5864zek1v/o21hEmT0dH/"
    "qXmt41CuwKSDo0CoDoV68ngKfv3uUAkNRKBZBdiwNI7oiRNwbjIP5+PxqKQYyIcEA+mOQF"
    "v2q6ik+AoTv4WzVhzUCRvjV96IXj/GNEwXtz2/mTx7U7GF0xFCwHz2zWCmvgimBMTebT98"
    "jgpwVTqH5/gbamJK5YTSutbvLSorngS6AJZwwr+sb0/fxJ5MFhBj0xubDyzKnFJTWcas0s"
    "V/rsiCaXD83m+/fnzXfvzy7arfPz9sW7cJZJXsqabq76H+mME9PN9VMQWkDdKGI7Q4F6Ws"
    "9WHuPZSredrYTpnENnjjRlCR3nxbIF+pqOpUC0nqieNi/yzEnNi/Q5iV6LA8v+F0AzqF9P"
    "CJt5FLOZrpjNhGKSN9Y8855EsGe6C4ZinzwSNFWUQHMlfWA8G7edQe8S0L+P5k3P++b9b5"
    "TA+SwHzGepKJ/xIE91G881+JqE+ZqAI1bUqAwHLrHTCOsL9JZ+qKbaZuB33Zn0OHyW5O2Q"
    "QrRtmqaKYox4uXoO6tPTPGbxNN0qnvL6pjsKWYTpzwLLeGVZBoJmysIoKseBOSWCu0IzXD"
    "RtW9euRqNBbIl+1ecWP8OH26segZehSyrpOLYmimOqLXSBH74W0kBsj4gWXX0fBFIDOlgx"
    "rJkI1GvfxolRjUtmmUf6IQfIvgZWw0JO+re9+0nn9i6GM7Wb9EqTlb5ypYnpKGwE/NGffA"
    "L0K/hrNOzxTmhYb/JXgz4TdLGlmNYLUdvoawfFQVGcGLARhVaBAm4guyPjklvoyENYc/IO"
    "2sg0Xn09qknP+iqf2bHuUivZsXFJ2bEH7Vj28BVhme4g1ikjKCCagksnWVzTMlJpHdvU6A"
    "DV0E1d/cVRrSXSgC8MdI381fErcMjakpRPXwE0DPCsOzp23vIewwbNCFitr4255Sx1DA3F"
    "I6LCr36zpNMa3zjuKyEU+LHMTVCYI0BEEtXYCtlrTUidBbcsSqHF5SSVlptK4/onP+J8x6"
    "6FvCI2dI+oC1CODKkE2hmUm1i8nu5lOw9n1E7njNoJzui/xbltH7+IzRauqjIIoVDq2Cmh"
    "+vGSjYfh5+HoD7YlyC1D4oTkoxklK0eTT73xJWD/Hk2/jUsQbaygwmaZz0Bfz1PV9ZzXVm"
    "8JUWC4hwL1HO/b59idhaPQWwr3zjPZI05SEkipwJZyUkXykkw6MJlEO8Va0g6xXFyyU3l5"
    "2akV6FR/pCkBNTQV7IdleUDpbZRyhvbfoYfxhSQ5exQcniRnj7Rji5KzkchgxjMKjKgvd/"
    "N5jAyIxZHAPuf6hbZRzR7+GahtUBoFa1f0tIeHgJwOgUqnpp/DKmuJ6ZGJOE4ZmarlknWo"
    "DabIsMwZQQZgC6AfpB3jFRCXKqCdk/z0xq2tD75MMMvsZT0bwojnCC8fvZTKPLNKhVnQqJ"
    "RknSXrXAHUVyiT58KWXRjjmJhcymYBjJbQxgshj5LOR8WlSpFSBwB498c5Ima64PoxLlnP"
    "9WNN1ou5vGtvVnTcxQLaAqd6gn5kTqcRwZqMjqzO6/05ifVb4lRO2HeD0fBjUJ0/qiO07K"
    "Yl2rJJh5cTk+AKwXUwxK7Ajcm31bOS3uNWT3d0ezfoTXrXgs2e++6n3vXDoHd9CcKPj2Yo"
    "cQnCj6S0M+z2WNXgU5kNnw855oYPqTPDh8SGjwFNk1h3B1uCA5OZ+xW8qNywkFzcEVI2ko"
    "s70o71H37/8XEV6ce9eXUJvjMBeRLvG8tG+sz8jF4TKwIxtxmJJ60e1mnsJim24UtImHGa"
    "RF6SvBry5pcxUe5xv0vwzMMWW6qt/G1NN+SLR6r9uzWtF6Q7JYwJINeW6lJ6gToCDQF1zF"
    "c5ySKRaTdpfm0FB9XXEsoTtFiSQWa/glF3DKjcb0DHYOE6GEwRWLo2eXrwouM5wHMEyP1t"
    "65mUOJZrqwgEd0xyy9tsWBgNTV+Y2GuqAN69vVcn+s4HQadyyQnMCtvrtBYkx5ybY472XC"
    "HsOUE5Wa7hmH0lpfgkcM7nMycaOfTp7d7t+BKQP4/mHZnUuuP+3aQ/Gl6C6LdHc9C5UkjB"
    "w2ByCVafy3jMp81cmQgyEhHwTjOdswNrnZceispIbkjIDQUQKd48U8K/ErcgA8LkkVHpME"
    "smRHZsXiZktUwvtbiOicolXgE+JO4fbUiJEFd0HLZVPcDzkiIJjYrxIt3Ofbdz3ctHi/hl"
    "SYUuRoqEml/VVcPeWZGbhJsuQCubB3kKq+U46U1quCp26TnsZ2i4yOMkRt3xCVAt20YqrX"
    "oCoKmR7+aTbi9YrwLGV5h02IgOfm+p1RzMR0T9ChEfnlwZmxyVlERHbqIjAnIC8vQopLhU"
    "PY/GnbVyuM1nrfTEaC3ebSaOGR3XZNXHRlcR71kgKp1ooRPtG6oyIAtEJcgpIBPrryF/9c"
    "X5PUjVF9BIgzgqyLs9nuRbv4W6IX3d6/ZvO4M37ZMWFxsRzaLKhSWm5TtPDwpPTXe+Q8/i"
    "dONpbMOM8bHUdP7aA4lWAWvS08VEZcBOHFqyMNXJLYofVuQEZVh3xp5GiFVxzogTlbTuoW"
    "ndwJgUHjC8pBwxWWd6Q7BK8OecrBwzhx4zcivkGBhzuRVypB2b2Ao5VKhRJSzvYSY8ufsk"
    "d5/qtvuUajK2gyQfUlo5S5EXTpExjCF635uA4cNgkG9DT4WmptOpcUubet2gvXop7V6291"
    "bYZOzzxQDMseGnqDGBHFt/NjS/Iw1AAyPbhPQHLICNMAGDRibPkcnyXbC2wRw6YEFw15cG"
    "rQQ1gq0w4/NW2kzd9gt3Nultyuz3hRhtsPPHtyH3AHPvAa6gK76lkhSty26g3FOpANJl9l"
    "SYlUlAeE/e3ki1E4FMzZbL75vnZ6EpoF+yBv89AXIgyCvKzq4UztDMiW2YorlaSpfM0Kw7"
    "ikOWaHRzuPimU1RS7jnJQ+JHSBsl+cB9RmtVpDOrQmGE6+3N/e68kZ4V8gVPBARGVJ2KRs"
    "/u2LWkB4zF/qR/9Djbifzbr1T414HoAVfSM6rLIjifLJv5eCxH0vrfBFonXCLF4iq1TcSw"
    "f6PJFsNMk9ELmV4jAUVoddIDFuNS23FRdu4c7iRcUeZVPCz5X8MEUXfjUbd3f98ffmwk7c"
    "7qIj3hGnxOyxF10+mzDFHef94O5RkHp/mSB2bkDkykiLItui4S9Em2TxmV25/Ov9tY4bfh"
    "VNqIPLFTJvE9LymtxRprYZf8OZCYpIyLOXRcjLVY0kVpuSCnuKzszAN35hPUDddGpIu0Ys"
    "dmOLmanD7Y9bkZyREdKUckY8aOomMTMWP7+LmDivRhFTi/kCDZkO+r4c+jnHBkX1SHNkgf"
    "GGxu+cE6W0kjGIQw1QvgYpE1UQdQHEYX4DYy0cQif3KhlzuOrjpxXz9LMcGhjqQywlEtWs"
    "sMhwqckyI2gbs0LKghLUxlCAiQLvmuezFAMeJXwBOXaSE1bsjntrOyJH5NXs1khUvn7Utp"
    "QEYRyZSJFUBdpkysespE6cMehasjjnOoxn5jPYmeNbEM/hpg80iG2iXy5l2buMpULIrBX6"
    "GLl62r5Xv2inXlM6xfq37x0mD4sQiWi5cuZompdOwAGz3r6OXXWI4q6Go0kzfCkK5QkkvX"
    "bTS4Puwhc4G6vzNfclEaVVKFfStgveNS9bTeO/mVPQ+Y1KQ26xBNz21Tj62Pdh5I2+mItm"
    "V+oI3zA8kkNjKJjdyrlklsKjZiZBKbYxozksw5TjJHBiQcRccK8/lXg6Sr46GABEWXZwt9"
    "e3vnBXN/VIjCiwcFeiBtikYNT2QJYghykLxBhMDOKd5dD8mdEbwlSNuf/wcJ797w"
)
