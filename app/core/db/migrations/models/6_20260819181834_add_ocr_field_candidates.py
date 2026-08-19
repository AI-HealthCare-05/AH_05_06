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
    "oCoKmR7+aTbi9YrwLGV5h02IgOfm+p1TwBdqkDPT2ILgSplE2OSkqiIzfREQE5AXl6FFJc"
    "qp5H485aOdzms1Z6YrQW7zYTx4yOa7LqY6OriPcsEJVOtNCJ9g1VGZAFohLkFJCJ9deQv/"
    "ri/B6k6gtopEEcFeTdHk/yrd9C3ZC+7nX7t53Bm/ZJi4uNiGZR5cIS0/KdpweFp6Y736Fn"
    "cbrxNLZhxvhYajp/7YFEq4A16eliojJgJw4tWZjq5BbFDytygjKsO2NPI8SqOGfEiUpa99"
    "C0bmBMCg8YXlKOmKwzvSFYJfhzTlaOmUOPGbkVcgyMudwKOdKOTWyFHCrUqBKW9zATntx9"
    "krtPddt9SjUZ20GSDymtnKXIC6fIGMYQve9NwPBhMMi3oadCU9Pp1LilTb1u0F69lHYv23"
    "srbDL2+WIA5tjwU9SYQI6tPxua35EGoIGRbUL6AxbARpiAQSOT58hk+S5Y22AOHbAguOtL"
    "g1aCGsFWmPF5K22mBjyHO5v0NsUCnTmMNtj549uQe4C59wBX0BXfUkmK1mU3UO6pVADpMn"
    "sqzMokILwnb2+k2olApmbL5ffN87PQFNAvWYP/ngA5EOQVZWdXCmdo5sQ2TNFcLaVLZmjW"
    "HcUhSzS6OVx80ykqKfec5CHxI6SNknzgPqO1KtKZVaEwwvX25n533kjPCvmCJwICI6pORa"
    "Nnd+xa0gPGYn/SP3qc7UT+7Vcq/OtA9IAr6RnVZRGcT5bNfDyWI2n9bwKtEy6RYnGV2iZi"
    "2L/RZIthpsnohUyvkYAitDrpAYtxqe24KDt3DncSrijzKh6W/K9hgqi78ajbu7/vDz82kn"
    "ZndZGecA0+p+WIuun0WYYo7z9vh/KMg9N8yQMzcgcmUkTZFl0XCfok26eMyu1P599trPDb"
    "cCptRJ7YKZP4npeU1mKNtbBL/hxITFLGxRw6LsZaLOmitFyQU1xWduaBO/MJ6oZrI9JFWr"
    "FjM5xcTU4f7PrcjOSIjpQjkjFjR9GxiZixffzcQUX6sAqcX0iQbMj31fDnUU44si+qQxuk"
    "Dww2t/xgna2kEQxCmOoFcLHImqgDKA6jC3AbmWhikT+50MsdR1eduK+fpZjgUEdSGeGoFq"
    "1lhkMFzkkRm8BdGhbUkBamMgQESJd8170YoBjxK+CJy7SQGjfkc9tZWRK/Jq9mssKl8/al"
    "NCCjiGTKxAqgLlMmVj1lovRhj8LVEcc5VGO/sZ5Ez5pYBn8NsHkkQ+0SefOuTVxlKhbF4K"
    "/QxcvW1fI9e8W68hnWr1W/eGkw/FgEy8VLF7PEVDp2gI2edfTyayxHFXQ1mskbYUhXKMml"
    "6zYaXB/2kLlA3d+ZL7kojSqpwr4VsN5xqXpa7538yp4HTGpSm3WIpue2qcfWRzsPpO10RN"
    "syP9DG+YFkEhuZxEbuVcskNhUbMTKJzTGNGUnmHCeZIwMSjqJjhfn8q0HS1fFQQIKiy7OF"
    "vr2984K5PypE4cWDAj2QNkWjhieyBDEEOUjeIEJg5xTvrofkzgjeEqTtz/8D9Jve8A=="
)
